"""Executable current-head admission binding for the future S2E LW2 task."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_lw2_readmission import (  # noqa: E402
    LW2_ADMISSION_PROFILE,
    canonical_claim_digest,
    lw2_contract_selected,
    lw2_protected_inventory,
    validate_lw2_contract_binding,
    validate_lw2_readmission_eligibility,
)
from agent_governance_command_capture_v2 import (  # noqa: E402
    capture_governed_command,
)
from agent_governance_command_replay import command_argv  # noqa: E402
from agent_governance_execution_policy import (  # noqa: E402
    requested_execution_binding,
)
from agent_governance_execution_dag import (  # noqa: E402
    execution_dag_digest,
    execution_node_core,
)
from agent_governance_pytest_provider import (  # noqa: E402
    GOVERNED_PYTEST_PREFIX,
    GOVERNED_PYTEST_REQUIRED_ARGS,
)
from agent_governance_registry import load_registry  # noqa: E402
from agent_governance_workflow_receipts import (  # noqa: E402
    build_controller_workflow_call_record,
)
from agent_governance_routing import route_task, task_contract_projection  # noqa: E402
from agent_governance_execution import (  # noqa: E402
    capture_repository_baseline,
    compile_context,
    materialize_context_artifact,
    validate_context_artifact,
)
from agent_governance_task_admission import (  # noqa: E402
    FileTaskAdmissionStore,
    acquire_task_admission,
    capture_task_admission_generation,
    continue_admitted_task,
    release_task_admission,
)
from agent_governance_capture import (  # noqa: E402
    NativeEvidenceMismatch,
    NativeEvidenceUnavailable,
)
import agent_governance_capture as capture_module  # noqa: E402
from agent_governance import main as governance_main  # noqa: E402
import agent_governance_task_admission as task_admission_module  # noqa: E402
from agent_governance_writer_lease import (  # noqa: E402
    FileWriterLeaseStore,
    acquire_writer_lease,
    filesystem_writer_lease_action as _filesystem_writer_lease_action,
    inspect_worktree,
    release_writer_lease,
    renew_writer_lease,
    validate_writer_lease,
)
import agent_governance_writer_lease as writer_lease_module  # noqa: E402
import git_loop_guard as git_guard  # noqa: E402


HEAD = "1" * 40
TREE = "2" * 40
LW2_FOCUSED_TEST_PATHS = [
    "tests/structure/test_agent_governance_context_pack_reachability.py",
    "tests/structure/test_agent_governance_s2e_launch_chain.py",
]
LW2_FOCUSED_TEST_TARGETS = [
    (
        "tests/structure/test_agent_governance_context_pack_reachability.py::"
        "test_active_state_contains_the_exact_empty_dispatch_projection"
    ),
    (
        "tests/structure/test_agent_governance_s2e_launch_chain.py::"
        "test_lw1_through_lw5_require_the_exact_unconsumed_prior_digest"
    ),
    (
        "tests/structure/test_agent_governance_s2e_launch_chain.py::"
        "test_lw2_rejects_a_predecessor_receipt_from_a_sibling_branch"
    ),
]
LW2_TRUST_CEILING = "ORCHESTRATOR_BOUND_STRUCTURAL_PROVENANCE_ONLY"
LW2_REPOSITORY_URL = "https://github.com/yunancun/Arcane-Equilibrium.git"
LW2_DESTINATION_REF = "refs/heads/main"
LW2_WRITABLE_PATH = (
    "helper_scripts/maintenance_scripts/"
    "agent_governance_s2e_launch_receipts.py"
)


def filesystem_writer_lease_action(**arguments):
    """Supply explicit publication coordinates in public-interface tests."""

    if arguments.get("action") == "publication-status":
        identity = inspect_worktree(arguments["repo"])
        arguments.setdefault("publication_phase", "publish")
        arguments.setdefault("publication_expected_branch", identity.branch)
        arguments.setdefault("publication_expected_head", identity.head)
    return _filesystem_writer_lease_action(**arguments)


@pytest.fixture(autouse=True)
def _offline_publication_remote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep publication regressions source-only and network-free."""

    def observed_head(repo: Path, repository_url: str, ref: str) -> str | None:
        if repository_url != LW2_REPOSITORY_URL:
            return None
        remote_ref = (
            "refs/remotes/origin/main"
            if ref == LW2_DESTINATION_REF
            else ref.replace("refs/heads/", "refs/remotes/origin/", 1)
        )
        completed = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repo), "rev-parse", remote_ref],
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip() if completed.returncode == 0 else None

    monkeypatch.setattr(
        writer_lease_module, "_canonical_remote_head", observed_head
    )


class _StrictExternalVerifier:
    def __init__(self, claim_payloads: dict[str, object]) -> None:
        identity = claim_payloads["lw2_combined_main_identity"]
        capture = claim_payloads["lw2_combined_main_unreachability_capture"]
        review = claim_payloads["lw2_independent_review"]
        command_capture = capture["command_capture"]
        call = review["workflow_call_record"]
        fragment = review["role_fragment"]
        self.expected = [
            {
                "schema_version": "lw2_publication_verification_request_v1",
                "repository_url": identity["repository_url"],
                "destination_ref": identity["destination_ref"],
                "head": identity["head"],
                "tree": identity["tree"],
                "publication_provenance": identity["publication_provenance"],
            },
            {
                "schema_version": (
                    "lw2_independent_review_verification_request_v1"
                ),
                "repository_url": identity["repository_url"],
                "destination_ref": identity["destination_ref"],
                "head": identity["head"],
                "tree": identity["tree"],
                "task_contract_digest": review["task_contract_digest"],
                "context_artifact_digest": review["context_artifact_digest"],
                "evidence_dag_digest": review["evidence_dag_digest"],
                "node_id": "independent_review",
                "capture_digest": command_capture["record_digest"],
                "reviewer_identity": "E2",
                "workflow_call_record_digest": call["record_digest"],
                "role_fragment_digest": _digest(fragment),
                "verdict": "PASS",
            },
        ]
        self.seen: list[dict[str, object]] = []

    def __call__(self, request: dict[str, object]) -> bool:
        position = len(self.seen)
        if position >= len(self.expected) or request != self.expected[position]:
            return False
        self.seen.append(deepcopy(request))
        return True


def _strict_external_verifier(
    claim_payloads: dict[str, object],
) -> _StrictExternalVerifier:
    return _StrictExternalVerifier(claim_payloads)


def _throwing_external_verifier(_request: dict[str, object]) -> bool:
    raise RuntimeError("trusted host unavailable")


def _digest(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _claims(
    *, head: str = HEAD, tree: str = TREE,
    reviewer: str = "E2", writer: str = "E1",
) -> tuple[dict[str, str], dict[str, object]]:
    publication = {
        "schema_version": "lw2_destination_publication_provenance_v1",
        "trust_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "provider": "github",
        "provider_record_id": f"refs/heads/main@{head}",
        "repository_url": LW2_REPOSITORY_URL,
        "destination_ref": LW2_DESTINATION_REF,
        "head": head,
        "tree": tree,
        "status": "PUBLISHED",
    }
    publication["record_digest"] = _digest(publication)
    identity = {
        "schema_version": "lw2_combined_main_identity_v2",
        "repository_url": LW2_REPOSITORY_URL,
        "destination_ref": LW2_DESTINATION_REF,
        "head": head,
        "tree": tree,
        "publication_provenance": publication,
    }
    capture = {
        "schema_version": "lw2_combined_main_unreachability_capture_v1",
        "head": head,
        "tree": tree,
        "status": "PASS",
        "command_capture_schema": "command_capture_v2",
        "governed": True,
        "permission": "read-only",
        "producer_identity": writer,
    }
    capture_digest = _digest(capture)
    review = {
        "schema_version": "lw2_independent_review_v1",
        "head": head,
        "tree": tree,
        "status": "PASS",
        "permission": "read-only",
        "governed": True,
        "reviewer_identity": reviewer,
        "writer_identity": writer,
        "reviewed_capture_digest": capture_digest,
    }
    payloads = {
        "lw2_combined_main_identity": identity,
        "lw2_combined_main_unreachability_capture": capture,
        "lw2_independent_review": review,
    }
    return (
        {key: _digest(value) for key, value in payloads.items()},
        payloads,
    )


def _git_value(repo: Path, expression: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", expression],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_output(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _clone_exact_head_as_main(source: Path, destination: Path) -> str:
    source_head = _git_value(source, "HEAD")
    subprocess.run(
        [
            "git", "clone", "--quiet", "--no-checkout",
            str(source), str(destination),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "--quiet", "-B", "main", source_head],
        cwd=destination,
        check=True,
    )
    assert _git_value(destination, "HEAD") == source_head
    return source_head


def _real_claims(repo: Path) -> tuple[dict[str, str], dict[str, object]]:
    head, tree = _git_value(repo, "HEAD"), _git_value(repo, "HEAD^{tree}")
    evidence_facts = {
        "task_shape": "review",
        "surfaces": ["python", "security"],
        "risk": "high",
        "uncertainty": "low",
        "side_effect_class": "none",
        "objective": "capture current combined-main LW2 unreachability",
        "scope": LW2_FOCUSED_TEST_PATHS,
        "dirty_scope": LW2_FOCUSED_TEST_PATHS,
        "verification_scope": LW2_FOCUSED_TEST_PATHS,
        "acceptance_criteria": ["governed focused unreachability suite passes"],
        "hard_stops": ["no runtime or trading effect"],
        "baseline": capture_repository_baseline(repo),
        "direct_interfaces": ["lw2_unreachability_capture_v1"],
        "previous_failure": "summary-only evidence was accepted",
    }
    routed = route_task(evidence_facts, repo=repo)
    capture_task = {
        "node_id": "lw2_combined_main_unreachability_capture",
        "role": "E3",
        "native_agent": "E3",
        "node_class": "verification",
        "permission": "read_only",
        "requires": [],
    }
    authoritative_dag = [
        *[
            execution_node_core(node)
            for node in routed["required_role_nodes"]
        ],
        capture_task,
    ]
    plan = compile_context(
        "E3", routed["task_facts"], root=repo,
        execution_dag=authoritative_dag,
    )
    context_artifact = materialize_context_artifact(plan)
    capture = capture_governed_command(
        native_agent="E3",
        node_id=capture_task["node_id"],
        context_artifact=context_artifact,
        argv=[
            *GOVERNED_PYTEST_PREFIX,
            *GOVERNED_PYTEST_REQUIRED_ARGS,
            "-q",
            *LW2_FOCUSED_TEST_TARGETS,
        ],
        root=repo,
        timeout_seconds=120,
    )
    capture_wrapper = {
        "schema_version": "lw2_combined_main_unreachability_capture_v1",
        "head": head,
        "tree": tree,
        "context_artifact_digest": capture["context_artifact_digest"],
        "task_contract_digest": capture["task_contract_digest"],
        "capture_digest": capture["record_digest"],
        "evidence_dag_digest": execution_dag_digest([
            capture_task,
            {
                "node_id": "independent_review",
                "role": "E2",
                "native_agent": "E2",
                "node_class": "verification",
                "permission": "read_only",
                "requires": [capture_task["node_id"]],
            },
        ]),
        "command_capture": capture,
    }
    review_payload = {
        "schema_version": "lw2_independent_review_judgment_v1",
        "status": "PASS",
        "reviewed_head": head,
        "reviewed_tree": tree,
        "reviewed_capture_digest": capture["record_digest"],
        "writer_native_identity": "E1",
        "trust_ceiling": LW2_TRUST_CEILING,
    }
    e2_context_artifact = materialize_context_artifact(
        compile_context(
            "E2", routed["task_facts"], root=repo,
            execution_dag=authoritative_dag,
        )
    )
    assert e2_context_artifact["task_contract_digest"] == (
        capture["task_contract_digest"]
    )
    judgment = {
        "work_status": "DONE",
        "gate_verdict": "PASS",
        "classification": "FACT",
        "confidence": "high",
        "summary": "current-head governed LW2 unreachability evidence passed review",
        "evidence_refs": [capture["record_digest"]],
        "concerns": [],
        "next_action": None,
        "payload": review_payload,
    }
    registry = load_registry()
    saved_models = registry["saved_workflow_model_policy"]
    call_id = "lw2-readmission:independent-review:attempt:1"
    call = build_controller_workflow_call_record(
        workflow_contract_digest=_digest({
            "schema_version": "lw2_independent_review_workflow_v1",
        }),
        logical_call_id=call_id,
        node_id="independent_review",
        payload_kind=registry["roles"]["E2"]["payload_kind"],
        attempt=1,
        retry_parent_call_id=None,
        phase="LW2Readmission",
        label="lw2-independent-review",
        requested={
            "logical_role": "E2",
            "platform": "claude_saved_workflow",
            "platform_requested_agent": "E2",
            "native_binding": {
                "logical_role": "E2",
                "native_agent": "E2",
                "node_class": "verification",
                "permission": "read_only",
            },
            **requested_execution_binding(registry),
            "model": saved_models["role_models"]["E2"],
            "effort": saved_models["role_efforts"]["E2"],
            "isolation": None,
            "node_class": "verification",
            "permission": "read_only",
        },
        prompt_digest=_digest({"review": capture["record_digest"]}),
        context_artifact_digest=e2_context_artifact["artifact_digest"],
        task_contract_digest=capture["task_contract_digest"],
        dirty_scope_digest=_digest(LW2_FOCUSED_TEST_PATHS),
        focus_digest=_digest(""),
        compiler_input_tokens_lower_bound=1,
        admitted_input_tokens_lower_bound=1,
        response_schema_digest=_digest({
            "schema_version": "lw2_independent_review_judgment_v1",
        }),
        started_at=datetime.now(timezone.utc).isoformat(),
        ended_at=datetime.now(timezone.utc).isoformat(),
        returned_null=False,
        parsed_result_digest=_digest(judgment),
        dag_digest=capture_wrapper["evidence_dag_digest"],
        requires=[capture_task["node_id"]],
        topological_wave=1,
        producer_generation={capture_task["node_id"]: capture["record_digest"]},
    )
    role_fragment = {
        "schema_version": "role_fragment_v1",
        "id": "fragment:lw2-independent-review",
        "node_id": "independent_review",
        "role": "E2",
        "task_contract_digest": capture["task_contract_digest"],
        "context_artifact_digest": e2_context_artifact["artifact_digest"],
        "producer_call_ref": call_id,
        "producer_call_receipt_digest": call["record_digest"],
        "producer_record_kind": "workflow_call_record_v1",
        **judgment,
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": "platform telemetry was not exposed",
        },
        "payload_kind": registry["roles"]["E2"]["payload_kind"],
    }
    publication = {
        "schema_version": "lw2_destination_publication_provenance_v1",
        "trust_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "provider": "github",
        "provider_record_id": f"refs/heads/main@{head}",
        "repository_url": LW2_REPOSITORY_URL,
        "destination_ref": LW2_DESTINATION_REF,
        "head": head,
        "tree": tree,
        "status": "PUBLISHED",
    }
    publication["record_digest"] = _digest(publication)
    identity = {
        "schema_version": "lw2_combined_main_identity_v2",
        "repository_url": LW2_REPOSITORY_URL,
        "destination_ref": LW2_DESTINATION_REF,
        "head": head,
        "tree": tree,
        "publication_provenance": publication,
    }
    review_wrapper = {
        "schema_version": "lw2_independent_review_v1",
        "head": head,
        "tree": tree,
        "context_artifact_digest": e2_context_artifact["artifact_digest"],
        "task_contract_digest": capture["task_contract_digest"],
        "workflow_call_record": call,
        "role_fragment": role_fragment,
        "trust_ceiling": LW2_TRUST_CEILING,
        "evidence_dag_digest": capture_wrapper["evidence_dag_digest"],
    }
    payloads = {
        "lw2_combined_main_identity": identity,
        "lw2_combined_main_unreachability_capture": capture_wrapper,
        "lw2_independent_review": review_wrapper,
    }
    return {key: _digest(value) for key, value in payloads.items()}, payloads


@pytest.fixture(scope="module")
def real_lw2_evidence(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict[str, str], dict[str, object]]:
    repo = tmp_path_factory.mktemp("lw2-real-evidence") / "repo"
    _clone_exact_head_as_main(ROOT, repo)
    subprocess.run(
        ["git", "remote", "set-url", "origin", LW2_REPOSITORY_URL],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=repo,
        check=True,
    )
    claim_inputs, claim_payloads = _real_claims(repo)
    return repo, claim_inputs, claim_payloads


JUDGMENT_FIELDS = {
    "work_status", "gate_verdict", "classification", "confidence",
    "summary", "evidence_refs", "concerns", "next_action", "payload",
}


def _rehash_record(record: dict[str, object]) -> None:
    record["record_digest"] = _digest({
        key: value for key, value in record.items()
        if key != "record_digest"
    })


def _refresh_review_record(payloads: dict[str, object]) -> None:
    review = payloads["lw2_independent_review"]
    call = review["workflow_call_record"]
    fragment = review["role_fragment"]
    call["parsed_result_digest"] = _digest({
        key: fragment[key] for key in JUDGMENT_FIELDS
    })
    _rehash_record(call)
    fragment["producer_call_receipt_digest"] = call["record_digest"]


def _refresh_capture_chain(payloads: dict[str, object]) -> None:
    capture = payloads["lw2_combined_main_unreachability_capture"]
    command_capture = capture["command_capture"]
    _rehash_record(command_capture)
    capture["capture_digest"] = command_capture["record_digest"]
    review = payloads["lw2_independent_review"]
    call = review["workflow_call_record"]
    fragment = review["role_fragment"]
    call["producer_generation"] = {
        "lw2_combined_main_unreachability_capture": (
            command_capture["record_digest"]
        ),
    }
    fragment["evidence_refs"] = [command_capture["record_digest"]]
    fragment["payload"]["reviewed_capture_digest"] = (
        command_capture["record_digest"]
    )
    _refresh_review_record(payloads)


def _claim_digests(payloads: dict[str, object]) -> dict[str, str]:
    return {key: _digest(value) for key, value in payloads.items()}


def _invalid_claims(
    case: str,
    *,
    claim_inputs: dict[str, str],
    claim_payloads: dict[str, object],
) -> tuple[dict[str, str], dict[str, object]]:
    claim_inputs = deepcopy(claim_inputs)
    claim_payloads = deepcopy(claim_payloads)
    if case.startswith("missing_"):
        key = case.removeprefix("missing_")
        claim_inputs.pop(key)
        claim_payloads.pop(key)
    elif case == "extra_claim":
        claim_payloads["extra"] = {"schema_version": "extra_v1"}
        claim_inputs["extra"] = _digest(claim_payloads["extra"])
    elif case == "payload_replacement":
        claim_payloads["lw2_combined_main_identity"]["tree"] = "9" * 40
    elif case == "malformed_raw_head":
        for payload in claim_payloads.values():
            payload["head"] = "A" * 40
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "stale_head":
        for payload in claim_payloads.values():
            payload["head"] = "3" * 40
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "stale_tree":
        for payload in claim_payloads.values():
            payload["tree"] = "4" * 40
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "stale_capture_head":
        claim_payloads["lw2_combined_main_unreachability_capture"]["head"] = "3" * 40
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "wrong_destination":
        identity = claim_payloads["lw2_combined_main_identity"]
        identity["destination_ref"] = "refs/heads/feature"
        publication = identity["publication_provenance"]
        publication["destination_ref"] = "refs/heads/feature"
        _rehash_record(publication)
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "unpublished_provenance":
        publication = claim_payloads[
            "lw2_combined_main_identity"
        ]["publication_provenance"]
        publication["status"] = "UNPUBLISHED"
        _rehash_record(publication)
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "capture_non_pass":
        command_capture = claim_payloads[
            "lw2_combined_main_unreachability_capture"
        ]["command_capture"]
        command_capture["exit_code"] = 1
        command_capture["result"] = "FAIL"
        _refresh_capture_chain(claim_payloads)
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "capture_non_governed":
        command_capture = claim_payloads[
            "lw2_combined_main_unreachability_capture"
        ]["command_capture"]
        command_capture["trust_tier"] = "CALLER_ASSERTED"
        _refresh_capture_chain(claim_payloads)
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "review_non_pass":
        fragment = claim_payloads[
            "lw2_independent_review"
        ]["role_fragment"]
        fragment["gate_verdict"] = "FAIL"
        fragment["payload"]["status"] = "FAIL"
        _refresh_review_record(claim_payloads)
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "review_self_identity":
        fragment = claim_payloads[
            "lw2_independent_review"
        ]["role_fragment"]
        fragment["payload"]["writer_native_identity"] = "E2"
        _refresh_review_record(claim_payloads)
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "wrong_reviewed_capture_digest":
        fragment = claim_payloads[
            "lw2_independent_review"
        ]["role_fragment"]
        fragment["payload"]["reviewed_capture_digest"] = "sha256:" + "f" * 64
        _refresh_review_record(claim_payloads)
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "stale_task_contract":
        review = claim_payloads["lw2_independent_review"]
        review["task_contract_digest"] = "sha256:" + "a" * 64
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "stale_context":
        review = claim_payloads["lw2_independent_review"]
        review["context_artifact_digest"] = "sha256:" + "b" * 64
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "stale_review_node":
        review = claim_payloads["lw2_independent_review"]
        call = review["workflow_call_record"]
        call["node_id"] = "copied_independent_review"
        _rehash_record(call)
        review["role_fragment"]["producer_call_receipt_digest"] = (
            call["record_digest"]
        )
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "other_argv":
        command_capture = claim_payloads[
            "lw2_combined_main_unreachability_capture"
        ]["command_capture"]
        command_capture["argv"] = [
            *GOVERNED_PYTEST_PREFIX,
            *GOVERNED_PYTEST_REQUIRED_ARGS,
            "-q",
            LW2_FOCUSED_TEST_TARGETS[0],
        ]
        command_capture["command"] = command_argv(
            command_capture["argv"]
        )[1]
        _refresh_capture_chain(claim_payloads)
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "malformed_rehashed_capture":
        command_capture = claim_payloads[
            "lw2_combined_main_unreachability_capture"
        ]["command_capture"]
        command_capture.pop("stderr")
        _refresh_capture_chain(claim_payloads)
        claim_inputs = _claim_digests(claim_payloads)
    elif case == "bare_reviewer_labels":
        review = claim_payloads["lw2_independent_review"]
        review["workflow_call_record"] = "E2"
        review["role_fragment"] = "E2"
        claim_inputs = _claim_digests(claim_payloads)
    else:
        raise AssertionError(case)
    return claim_inputs, claim_payloads


def test_real_capture_and_review_are_eligible_only(
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, claim_inputs, claim_payloads = real_lw2_evidence
    head, tree = _git_value(repo, "HEAD"), _git_value(repo, "HEAD^{tree}")

    assert validate_lw2_readmission_eligibility(
        admission_profile=LW2_ADMISSION_PROFILE,
        claim_inputs=claim_inputs,
        claim_payloads=claim_payloads,
        current_head=head,
        current_tree=tree,
        repo=repo,
        external_evidence_verifier=_strict_external_verifier(claim_payloads),
    ) is True


@pytest.mark.parametrize(
    "writer_identity", ["E2", "worker", "E2/worker", "UNKNOWN", "E3"]
)
def test_lw2_writer_identity_must_resolve_to_a_registered_work_writer_before_external_verification(
    writer_identity: str,
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, _, base_payloads = real_lw2_evidence
    claim_payloads = deepcopy(base_payloads)
    fragment = claim_payloads["lw2_independent_review"]["role_fragment"]
    fragment["payload"]["writer_native_identity"] = writer_identity
    _refresh_review_record(claim_payloads)
    claim_inputs = _claim_digests(claim_payloads)
    external_requests: list[dict[str, object]] = []

    def external_verifier(request: dict[str, object]) -> bool:
        external_requests.append(deepcopy(request))
        return True

    with pytest.raises(ValueError, match="registered work writer"):
        validate_lw2_readmission_eligibility(
            admission_profile=LW2_ADMISSION_PROFILE,
            claim_inputs=claim_inputs,
            claim_payloads=claim_payloads,
            current_head=_git_value(repo, "HEAD"),
            current_tree=_git_value(repo, "HEAD^{tree}"),
            repo=repo,
            external_evidence_verifier=external_verifier,
        )
    assert external_requests == []


def test_lw2_native_writer_identity_binds_to_its_logical_admission_owner(
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, _, base_payloads = real_lw2_evidence
    claim_payloads = deepcopy(base_payloads)
    fragment = claim_payloads["lw2_independent_review"]["role_fragment"]
    fragment["payload"]["writer_native_identity"] = "PA-design-writer"
    _refresh_review_record(claim_payloads)
    claim_inputs = _claim_digests(claim_payloads)

    trusted_verifier = _strict_external_verifier(claim_payloads)
    assert validate_lw2_readmission_eligibility(
        admission_profile=LW2_ADMISSION_PROFILE,
        claim_inputs=claim_inputs,
        claim_payloads=claim_payloads,
        current_head=_git_value(repo, "HEAD"),
        current_tree=_git_value(repo, "HEAD^{tree}"),
        expected_writer_identity="PA",
        repo=repo,
        external_evidence_verifier=trusted_verifier,
    ) is True
    assert trusted_verifier.seen == trusted_verifier.expected

    for wrong_owner in ("PA-design-writer", "E1"):
        rejected_verifier = _strict_external_verifier(claim_payloads)
        with pytest.raises(ValueError, match="differs from admission owner"):
            validate_lw2_readmission_eligibility(
                admission_profile=LW2_ADMISSION_PROFILE,
                claim_inputs=claim_inputs,
                claim_payloads=claim_payloads,
                current_head=_git_value(repo, "HEAD"),
                current_tree=_git_value(repo, "HEAD^{tree}"),
                expected_writer_identity=wrong_owner,
                repo=repo,
                external_evidence_verifier=rejected_verifier,
            )
        assert rejected_verifier.seen == []


def test_structural_review_and_publication_claims_require_a_trusted_host(
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, claim_inputs, claim_payloads = real_lw2_evidence
    with pytest.raises(ValueError, match="out-of-band trusted verifier"):
        validate_lw2_readmission_eligibility(
            admission_profile=LW2_ADMISSION_PROFILE,
            claim_inputs=claim_inputs,
            claim_payloads=claim_payloads,
            current_head=_git_value(repo, "HEAD"),
            current_tree=_git_value(repo, "HEAD^{tree}"),
            repo=repo,
        )


@pytest.mark.parametrize(
    "verifier",
    [None, lambda _request: False, _throwing_external_verifier],
)
def test_none_false_or_throwing_trusted_verifier_fails_closed(
    verifier: object,
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, claim_inputs, claim_payloads = real_lw2_evidence
    with pytest.raises(ValueError, match="out-of-band trusted verifier"):
        validate_lw2_readmission_eligibility(
            admission_profile=LW2_ADMISSION_PROFILE,
            claim_inputs=claim_inputs,
            claim_payloads=claim_payloads,
            current_head=_git_value(repo, "HEAD"),
            current_tree=_git_value(repo, "HEAD^{tree}"),
            repo=repo,
            external_evidence_verifier=verifier,
        )


def test_strict_verifier_rejects_unknown_extra_and_out_of_order_requests(
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    _, _, claim_payloads = real_lw2_evidence
    verifier = _strict_external_verifier(claim_payloads)
    publication, review = deepcopy(verifier.expected)
    unknown = deepcopy(publication)
    unknown["schema_version"] = "unknown_verification_request_v1"
    extra = {**publication, "caller_asserted": True}

    assert verifier(unknown) is False
    assert verifier(extra) is False
    assert verifier(review) is False
    assert verifier(publication) is True
    assert verifier(review) is True
    assert verifier(review) is False


def test_handwritten_summary_only_lw2_claims_are_ineligible(
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, _, trusted_claim_payloads = real_lw2_evidence
    head, tree = _git_value(repo, "HEAD"), _git_value(repo, "HEAD^{tree}")
    claim_inputs, claim_payloads = _claims(head=head, tree=tree)

    with pytest.raises(ValueError, match="complete command_capture_v2"):
        validate_lw2_readmission_eligibility(
            admission_profile=LW2_ADMISSION_PROFILE,
            claim_inputs=claim_inputs,
            claim_payloads=claim_payloads,
            current_head=head,
            current_tree=tree,
            repo=repo,
            external_evidence_verifier=_strict_external_verifier(
                trusted_claim_payloads
            ),
        )


@pytest.mark.parametrize(
    "case",
    [
        "missing_lw2_combined_main_identity",
        "missing_lw2_combined_main_unreachability_capture",
        "missing_lw2_independent_review",
        "extra_claim",
        "payload_replacement",
        "malformed_raw_head",
        "stale_head",
        "stale_tree",
        "stale_capture_head",
        "wrong_destination",
        "unpublished_provenance",
        "capture_non_pass",
        "capture_non_governed",
        "review_non_pass",
        "review_self_identity",
        "wrong_reviewed_capture_digest",
        "stale_task_contract",
        "stale_context",
        "stale_review_node",
        "other_argv",
        "malformed_rehashed_capture",
        "bare_reviewer_labels",
    ],
)
def test_lw2_pure_validator_fails_closed_for_every_binding_break(
    case: str,
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, base_inputs, base_payloads = real_lw2_evidence
    claim_inputs, claim_payloads = _invalid_claims(
        case,
        claim_inputs=base_inputs,
        claim_payloads=base_payloads,
    )
    with pytest.raises(ValueError):
        validate_lw2_readmission_eligibility(
            admission_profile=LW2_ADMISSION_PROFILE,
            claim_inputs=claim_inputs,
            claim_payloads=claim_payloads,
            current_head=_git_value(repo, "HEAD"),
            current_tree=_git_value(repo, "HEAD^{tree}"),
            repo=repo,
            external_evidence_verifier=_strict_external_verifier(base_payloads),
        )


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("feature_branch", "local branch main"),
        ("detached_head", "local merged-main identity is unavailable"),
        ("unpublished_head", "origin/main == HEAD"),
        ("wrong_origin", "exact origin URL"),
    ],
)
def test_lw2_local_checkout_must_be_exact_published_origin_main(
    case: str,
    error: str,
    tmp_path: Path,
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    source, claim_inputs, claim_payloads = real_lw2_evidence
    repo = tmp_path / case
    subprocess.run(
        ["git", "clone", "--quiet", str(source), str(repo)], check=True,
    )
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "remote", "set-url", "origin", LW2_REPOSITORY_URL],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=repo,
        check=True,
    )
    if case == "feature_branch":
        subprocess.run(["git", "branch", "-M", "feature"], cwd=repo, check=True)
    elif case == "detached_head":
        subprocess.run(["git", "checkout", "--detach", "-q"], cwd=repo, check=True)
    elif case == "unpublished_head":
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/main", "HEAD^"],
            cwd=repo,
            check=True,
        )
    elif case == "wrong_origin":
        subprocess.run(
            [
                "git", "remote", "set-url", "origin",
                "https://example.invalid/repo.git",
            ],
            cwd=repo,
            check=True,
        )
    else:
        raise AssertionError(case)

    with pytest.raises(ValueError, match=error):
        validate_lw2_readmission_eligibility(
            admission_profile=LW2_ADMISSION_PROFILE,
            claim_inputs=claim_inputs,
            claim_payloads=claim_payloads,
            current_head=_git_value(repo, "HEAD"),
            current_tree=_git_value(repo, "HEAD^{tree}"),
            repo=repo,
            external_evidence_verifier=_strict_external_verifier(claim_payloads),
        )


def _route_facts(
    repo: Path,
    claim_inputs: dict[str, str],
    claim_payloads: dict[str, object],
    *,
    dirty_scope: list[str] | None = None,
) -> dict[str, object]:
    admitted_dirty_scope = dirty_scope or [LW2_WRITABLE_PATH]
    return {
        "task_shape": "implementation",
        "surfaces": ["python", "governance"],
        "risk": "high",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "objective": "implement the separately admitted future S2E LW2 source unit",
        "scope": admitted_dirty_scope,
        "dirty_scope": admitted_dirty_scope,
        "baseline": capture_repository_baseline(repo),
        "acceptance_criteria": ["fresh LW2 evidence is bound before work"],
        "hard_stops": ["no runtime or trading effect"],
        "direct_interfaces": ["S2E-LW2"],
        "work_item_id": "S2E-LW2",
        "lane_id": "S2E.2b-2",
        "previous_failure": "fresh combined-main evidence was not executable",
        "admission_profile": LW2_ADMISSION_PROFILE,
        "claim_inputs": deepcopy(claim_inputs),
        "claim_payloads": deepcopy(claim_payloads),
    }


def test_lw2_route_validates_current_claims_before_constructing_the_dag(
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, claim_inputs, claim_payloads = real_lw2_evidence
    facts = _route_facts(repo, claim_inputs, claim_payloads)

    routed = route_task(
        facts,
        repo=repo,
        external_evidence_verifier=_strict_external_verifier(claim_payloads),
    )

    assert routed["task_facts"]["admission_profile"] == LW2_ADMISSION_PROFILE
    assert task_contract_projection(routed["task_facts"])["claim_payloads"] == (
        facts["claim_payloads"]
    )
    missing = dict(facts)
    missing["claim_inputs"] = dict(facts["claim_inputs"])
    missing["claim_payloads"] = dict(facts["claim_payloads"])
    missing["claim_inputs"].pop("lw2_independent_review")
    missing["claim_payloads"].pop("lw2_independent_review")
    with pytest.raises(ValueError, match="exact three"):
        route_task(missing, repo=repo)


def test_lw2_route_rejects_caller_narrowing_to_unprotected_dirty_scope(
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, claim_inputs, claim_payloads = real_lw2_evidence
    facts = _route_facts(repo, claim_inputs, claim_payloads)
    facts["dirty_scope"] = [
        "helper_scripts/maintenance_scripts/agent_governance_lw2_readmission.py"
    ]

    with pytest.raises(ValueError, match="protected-only dirty_scope"):
        route_task(
            facts,
            repo=repo,
            external_evidence_verifier=_strict_external_verifier(claim_payloads),
        )


def test_lw2_route_keeps_current_inventory_out_of_contract_shape_authority(
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, claim_inputs, claim_payloads = real_lw2_evidence
    facts = _route_facts(repo, claim_inputs, claim_payloads)
    missing = (
        "program_code/ml_training/"
        "aiml_gate_receipt_s2e_missing_inventory.json"
    )
    facts["scope"] = [missing]
    facts["dirty_scope"] = [missing]

    routed = route_task(
        facts,
        repo=repo,
        external_evidence_verifier=_strict_external_verifier(claim_payloads),
    )
    contract = task_contract_projection(routed["task_facts"])

    assert contract["dirty_scope"] == [missing]
    validate_lw2_contract_binding(
        contract,
        task_id="S2E-LW2",
        repo=repo,
    )


@pytest.mark.parametrize(
    "case",
    [
        "missing_lw2_combined_main_identity",
        "missing_lw2_combined_main_unreachability_capture",
        "missing_lw2_independent_review",
        "extra_claim",
        "payload_replacement",
        "malformed_raw_head",
        "stale_head",
        "stale_tree",
        "stale_capture_head",
        "wrong_destination",
        "unpublished_provenance",
        "capture_non_pass",
        "capture_non_governed",
        "review_non_pass",
        "review_self_identity",
        "wrong_reviewed_capture_digest",
        "stale_task_contract",
        "stale_context",
        "stale_review_node",
        "other_argv",
        "malformed_rehashed_capture",
        "bare_reviewer_labels",
    ],
)
def test_every_invalid_lw2_route_stops_before_returning_a_dag(
    case: str,
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, base_inputs, base_payloads = real_lw2_evidence
    claim_inputs, claim_payloads = _invalid_claims(
        case,
        claim_inputs=base_inputs,
        claim_payloads=base_payloads,
    )
    facts = _route_facts(repo, claim_inputs, claim_payloads)
    dag = None
    with pytest.raises(ValueError):
        dag = route_task(
            facts,
            repo=repo,
            external_evidence_verifier=_strict_external_verifier(base_payloads),
        )
    assert dag is None


def test_ordinary_contract_defaults_remain_context_and_schema_compatible() -> None:
    routed = route_task({
        "task_shape": "implementation",
        "surfaces": ["python"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "objective": "verify the widened ordinary task contract",
        "scope": [
            "helper_scripts/maintenance_scripts/agent_governance_routing.py"
        ],
        "dirty_scope": [
            "helper_scripts/maintenance_scripts/agent_governance_routing.py"
        ],
        "baseline": capture_repository_baseline(ROOT),
        "acceptance_criteria": ["ordinary task contracts remain compatible"],
        "hard_stops": ["no runtime effect"],
        "direct_interfaces": ["task_contract_projection"],
        "previous_failure": "none",
    })
    assert routed["task_facts"]["admission_profile"] is None
    assert routed["task_facts"]["work_item_id"] is None
    assert routed["task_facts"]["lane_id"] is None
    assert routed["task_facts"]["claim_payloads"] == {}
    contract = task_contract_projection(routed["task_facts"])
    assert contract["admission_profile"] is None
    assert contract["work_item_id"] is None
    assert contract["lane_id"] is None
    assert contract["claim_payloads"] == {}

    plan = compile_context("E1", routed["task_facts"], root=ROOT)
    artifact = materialize_context_artifact(plan)
    validation = validate_context_artifact(
        artifact,
        expected_task_facts=routed["task_facts"],
    )
    assert validation["errors"] == []


def _ordinary_route_facts() -> dict[str, object]:
    return {
        "task_shape": "implementation",
        "surfaces": ["python"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "objective": "ordinary source repair",
        "scope": ["helper_scripts/maintenance_scripts/agent_governance_routing.py"],
        "dirty_scope": [
            "helper_scripts/maintenance_scripts/agent_governance_routing.py"
        ],
        "direct_interfaces": [],
    }


@pytest.mark.parametrize(
    "signal",
    [
        {"work_item_id": "S2E-LW2"},
        {"work_item_id": "S2E.LW2"},
        {"work_item_id": "S2E_LW2"},
        {"work_item_id": "S2E:LW2"},
        {"lane_id": "S2E.2b-2"},
        {"lane_id": "S2E.2b-2B"},
        {"lane_id": "P0-AIML-LONG-LIVED-RUNTIME-REPAIR"},
        {"direct_interfaces": ["S2E-LW2"]},
        {
            "direct_interfaces": [
                "S2E_2B_2B_HOST_RUNNER_CHECKPOINT_READY"
            ]
        },
        {
            "scope": [
                "helper_scripts/maintenance_scripts/"
                "agent_governance_s2_5_host_runner.py"
            ],
            "dirty_scope": [
                "helper_scripts/maintenance_scripts/"
                "agent_governance_s2_5_host_runner.py"
            ],
        },
        {
            "scope": [
                "program_code/ml_training/schemas/aiml_gate_receipts/"
                "s2e_launch_wave_receipt_v1.schema.json"
            ],
            "dirty_scope": [
                "program_code/ml_training/schemas/aiml_gate_receipts/"
                "s2e_launch_wave_receipt_v1.schema.json"
            ],
        },
    ],
)
def test_any_lw2_signal_selects_and_requires_the_exact_contract_before_dag(
    signal: dict[str, object],
) -> None:
    facts = {**_ordinary_route_facts(), **signal}
    assert lw2_contract_selected(facts) is True
    with pytest.raises(ValueError, match="LW2 selected contract requires"):
        route_task(facts)


def test_objective_text_alone_never_selects_lw2() -> None:
    facts = _ordinary_route_facts()
    facts["objective"] = "please implement S2E-LW2 after readmission"

    assert lw2_contract_selected(facts) is False
    routed = route_task(facts)
    assert routed["task_facts"]["work_item_id"] is None
    assert routed["task_facts"]["lane_id"] is None


def test_governed_evidence_clone_attaches_detached_source_head_as_main(
    tmp_path: Path,
) -> None:
    source = tmp_path / "detached-source"
    _clone_exact_head_as_main(ROOT, source)
    exact_head = _git_value(source, "HEAD")
    subprocess.run(
        ["git", "checkout", "--quiet", "--detach", exact_head],
        cwd=source,
        check=True,
    )
    advertised_refs = _git_output(
        source, "for-each-ref", "--format=%(refname)"
    ).splitlines()
    for ref in advertised_refs:
        subprocess.run(
            ["git", "update-ref", "-d", ref],
            cwd=source,
            check=True,
        )
    assert _git_output(source, "for-each-ref") == ""
    materialized = _clone_evidence_repo(source, tmp_path)

    assert _git_value(materialized, "HEAD") == exact_head
    assert subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=materialized,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == "main"
    assert _git_value(materialized, "refs/remotes/origin/main") == exact_head
    assert _git_output(materialized, "remote", "get-url", "origin") == (
        LW2_REPOSITORY_URL
    )


def test_lw2_protected_inventory_is_complete_and_deterministic() -> None:
    inventory = lw2_protected_inventory(ROOT)
    policy = load_registry()["lw2_readmission_policy"]

    assert inventory == tuple(sorted(inventory))
    assert len(inventory) == 25
    assert set(policy["protected_scope_paths"]).issubset(inventory)
    for prefix in policy["protected_scope_prefixes"]:
        assert any(path.startswith(prefix) for path in inventory)


@pytest.fixture(scope="module")
def real_lw2_contract(
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> tuple[Path, dict[str, object]]:
    repo, claim_inputs, claim_payloads = real_lw2_evidence
    routed = route_task(
        _route_facts(repo, claim_inputs, claim_payloads),
        repo=repo,
        external_evidence_verifier=_strict_external_verifier(claim_payloads),
    )
    return repo, task_contract_projection(routed["task_facts"])


def _clone_evidence_repo(source: Path, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _clone_exact_head_as_main(source, repo)
    subprocess.run(
        ["git", "config", "user.email", "lw2-test@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "LW2 Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "set-url", "origin", LW2_REPOSITORY_URL],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=repo,
        check=True,
    )
    return repo


def _linked_main_evidence_repo(source: Path, tmp_path: Path) -> Path:
    control = _clone_evidence_repo(source, tmp_path)
    subprocess.run(
        ["git", "branch", "-M", "holding"], cwd=control, check=True,
    )
    repo = tmp_path / "linked-main"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "main", str(repo), "HEAD"],
        cwd=control,
        check=True,
    )
    return repo


def _admitted_lw2_publication_feature(
    *,
    source: Path,
    contract: dict[str, object],
    tmp_path: Path,
    branch: str,
    marker: str,
) -> tuple[Path, dict[str, object], dict[str, object]]:
    repo = _linked_main_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    subprocess.run(
        ["git", "switch", "-q", "-c", branch], cwd=repo, check=True
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    governed_source = repo / LW2_WRITABLE_PATH
    governed_source.write_text(
        governed_source.read_text(encoding="utf-8") + f"\n# {marker}\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "--", LW2_WRITABLE_PATH], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", marker], cwd=repo, check=True
    )
    return repo, admission, acquired


def test_lw2_inventory_includes_untracked_nonignored_prefix_members(
    tmp_path: Path,
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    source, _, _ = real_lw2_evidence
    repo = _clone_evidence_repo(source, tmp_path)
    added = (
        "program_code/ml_training/"
        "aiml_gate_receipt_s2e_new_untracked.json"
    )
    (repo / added).write_text("{}\n", encoding="utf-8")

    assert added in lw2_protected_inventory(repo)


def _assert_no_admission_or_lease(repo: Path) -> None:
    identity = inspect_worktree(repo)
    store = FileTaskAdmissionStore(identity.common_dir)
    assert store.read()["admissions"] == {}
    assert store.state_path.exists() is False
    assert store.lock_path.exists() is False
    lease_store = FileWriterLeaseStore(identity.common_dir)
    assert lease_store.read()["leases"] == {}
    assert lease_store.state_path.exists() is False


@pytest.mark.parametrize(
    "deleted",
    [
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_s2e_launch_receipts.py"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_s2_5_attestation.py"
        ),
    ],
    ids=["exact", "prefix"],
)
def test_lw2_public_admission_and_writer_lifecycle_accept_owned_tracked_deletion(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
    deleted: str,
) -> None:
    source, _ = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    original = (repo / deleted).read_bytes()
    (repo / deleted).unlink()
    claim_inputs, claim_payloads = _real_claims(repo)
    routed = route_task(
        _route_facts(
            repo,
            claim_inputs,
            claim_payloads,
            dirty_scope=[deleted],
        ),
        repo=repo,
        external_evidence_verifier=_strict_external_verifier(claim_payloads),
    )
    owned_contract = task_contract_projection(routed["task_facts"])

    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=owned_contract,
        external_evidence_verifier=_strict_external_verifier(
            owned_contract["claim_payloads"]
        ),
    )

    assert admission["status"] == "PASS"
    assert deleted in admission["admission"]["accepted_generation"]["scope"]
    subprocess.run(
        ["git", "switch", "-q", "-c", f"agent/lw2-{deleted.rsplit('/', 1)[-1]}"],
        cwd=repo,
        check=True,
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    assert acquired["status"] == "PASS"
    lease_id = acquired["lease"]["lease_id"]
    for action in ("status", "renew"):
        current = filesystem_writer_lease_action(
            action=action,
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            lease_id=lease_id,
            admission_id=admission["admission_id"],
        )
        assert current["status"] == "PASS"

    (repo / deleted).write_bytes(original)
    restored = filesystem_writer_lease_action(
        action="status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=lease_id,
        admission_id=admission["admission_id"],
    )
    assert restored["status"] == "FAIL"
    assert restored["reasons"] == ["TASK_ADMISSION_GENERATION_MISMATCH"]
    (repo / deleted).write_bytes(original + b"\n# mutation after admission\n")
    mutated = filesystem_writer_lease_action(
        action="renew",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=lease_id,
        admission_id=admission["admission_id"],
    )
    assert mutated["status"] == "FAIL"
    assert mutated["reasons"] == ["TASK_ADMISSION_GENERATION_MISMATCH"]


def test_lw2_task_admission_revalidates_current_head_before_store_mutation(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _clone_evidence_repo(source, tmp_path)
    (repo / "lw2-head-advance.txt").write_text(
        "advance\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "lw2-head-advance.txt"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-m", "advance head"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    with pytest.raises(ValueError, match="not current repository HEAD/tree"):
        acquire_task_admission(
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            task_contract=contract,
            external_evidence_verifier=_strict_external_verifier(
                contract["claim_payloads"]
            ),
        )

    _assert_no_admission_or_lease(repo)


def test_lw2_task_admission_replays_before_store_and_rejects_dirty_generation(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _clone_evidence_repo(source, tmp_path)
    governed_source = repo / LW2_WRITABLE_PATH
    governed_source.write_text(
        governed_source.read_text(encoding="utf-8") + "\n# dirty generation\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="stale before replay"):
        acquire_task_admission(
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            task_contract=deepcopy(contract),
            external_evidence_verifier=_strict_external_verifier(
                contract["claim_payloads"]
            ),
        )

    _assert_no_admission_or_lease(repo)


def test_lw2_task_admission_recaptures_generation_inside_store_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _clone_evidence_repo(source, tmp_path)
    original_update = FileTaskAdmissionStore.update

    def mutate_after_replay(
        store: FileTaskAdmissionStore,
        mutation: object,
    ) -> dict[str, object]:
        governed_source = repo / LW2_WRITABLE_PATH
        governed_source.write_text(
            governed_source.read_text(encoding="utf-8")
            + "\n# post replay pre-store mutation\n",
            encoding="utf-8",
        )
        return original_update(store, mutation)

    monkeypatch.setattr(FileTaskAdmissionStore, "update", mutate_after_replay)
    with pytest.raises(ValueError, match="changed after replay before admission store"):
        acquire_task_admission(
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            task_contract=deepcopy(contract),
            external_evidence_verifier=_strict_external_verifier(
                contract["claim_payloads"]
            ),
        )

    identity = inspect_worktree(repo)
    assert FileTaskAdmissionStore(identity.common_dir).read()["admissions"] == {}
    assert FileTaskAdmissionStore(identity.common_dir).state_path.exists() is False
    assert FileWriterLeaseStore(identity.common_dir).read()["leases"] == {}


def test_lw2_task_admission_preserves_unavailable_locked_recapture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _clone_evidence_repo(source, tmp_path)
    native_capture = task_admission_module.capture_task_admission_generation
    capture_count = 0

    def unavailable_after_initial_capture(*args, **kwargs):
        nonlocal capture_count
        capture_count += 1
        if capture_count == 1:
            return native_capture(*args, **kwargs)
        raise NativeEvidenceUnavailable("injected locked native recapture")

    monkeypatch.setattr(
        task_admission_module,
        "capture_task_admission_generation",
        unavailable_after_initial_capture,
    )
    with pytest.raises(
        NativeEvidenceUnavailable,
        match=(
            "LW2 repository generation unavailable after replay before "
            "admission store"
        ),
    ):
        acquire_task_admission(
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            task_contract=deepcopy(contract),
            external_evidence_verifier=_strict_external_verifier(
                contract["claim_payloads"]
            ),
        )

    assert capture_count == 2
    store = FileTaskAdmissionStore(inspect_worktree(repo).common_dir)
    assert store.read()["admissions"] == {}
    assert store.state_path.exists() is False


def test_lw2_route_cli_returns_typed_failure_without_a_dag(
    capsys: pytest.CaptureFixture[str],
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, claim_inputs, claim_payloads = real_lw2_evidence
    facts = _route_facts(repo, claim_inputs, claim_payloads)
    facts["claim_inputs"] = dict(facts["claim_inputs"])
    facts["claim_payloads"] = dict(facts["claim_payloads"])
    facts["claim_inputs"].pop("lw2_combined_main_identity")
    facts["claim_payloads"].pop("lw2_combined_main_identity")

    exit_code = governance_main([
        "route", "--repo", str(repo), json.dumps(facts),
    ])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert result["status"] == "FAIL"
    assert "exact three" in result["error"]
    assert "nodes" not in result
    assert "dag_digest" not in result


def test_eligible_temp_repo_admission_never_auto_creates_a_writer_lease(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _clone_evidence_repo(source, tmp_path)
    result = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )

    assert result["status"] == "PASS"
    common_dir = inspect_worktree(repo).common_dir
    records = FileTaskAdmissionStore(common_dir).read()["admissions"]
    record = next(iter(records.values()))
    assert record["accepted_generation"] == result["admission"]["accepted_generation"]
    assert record["accepted_generation"]["source_head"] == _git_value(repo, "HEAD")
    assert record["accepted_generation"]["source_tree"] == _git_value(
        repo, "HEAD^{tree}"
    )
    assert record["accepted_generation"]["scope"] == list(
        lw2_protected_inventory(repo)
    )
    assert set(contract["dirty_scope"]).issubset(
        record["accepted_generation"]["scope"]
    )
    lease_store = FileWriterLeaseStore(common_dir)
    assert lease_store.read()["leases"] == {}
    assert lease_store.state_path.exists() is False


def test_lw2_continuation_revalidates_generation_before_advancing(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _clone_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    untracked_protected = (
        repo / "program_code" / "ml_training"
        / "aiml_gate_receipt_s2e_continuation_drift.json"
    )
    untracked_protected.write_text("{}\n", encoding="utf-8")

    continued = continue_admitted_task(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
        work_status="ACTIVE",
    )

    assert continued["status"] == "FAIL"
    assert continued["reasons"] == ["TASK_ADMISSION_GENERATION_MISMATCH"]
    record = next(iter(
        FileTaskAdmissionStore(inspect_worktree(repo).common_dir)
        .read()["admissions"].values()
    ))
    assert record["state"] == "ACTIVE"
    assert record["last_snapshot"]["round"] == 0


@pytest.mark.parametrize(
    ("error_type", "expected_reason"),
    [
        (NativeEvidenceUnavailable, "TASK_ADMISSION_GENERATION_UNAVAILABLE"),
        (NativeEvidenceMismatch, "TASK_ADMISSION_GENERATION_MISMATCH"),
    ],
    ids=["unavailable", "mismatch"],
)
def test_lw2_continuation_preserves_native_generation_failure_taxonomy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    real_lw2_contract: tuple[Path, dict[str, object]],
    error_type: type[ValueError],
    expected_reason: str,
) -> None:
    source, contract = real_lw2_contract
    repo = _clone_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )

    def fail_generation(*_args, **_kwargs):
        raise error_type("injected native generation observation")

    monkeypatch.setattr(
        task_admission_module,
        "capture_task_admission_generation",
        fail_generation,
    )
    direct = continue_admitted_task(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
        work_status="ACTIVE",
    )
    assert direct["status"] == "FAIL"
    assert direct["reasons"] == [expected_reason]

    exit_code = governance_main([
        "continuation",
        json.dumps({
            "repo": str(repo),
            "task_id": "S2E-LW2",
            "owner": "E1",
            "admission_id": admission["admission_id"],
            "work_status": "ACTIVE",
        }),
    ])
    cli = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert cli["status"] == "FAIL"
    assert cli["reasons"] == [expected_reason]
    record = next(iter(
        FileTaskAdmissionStore(inspect_worktree(repo).common_dir)
        .read()["admissions"].values()
    ))
    assert record["state"] == "ACTIVE"
    assert record["last_snapshot"]["round"] == 0


def test_direct_lw2_lease_requires_exact_admission_token_and_generation(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    assert admission["status"] == "PASS"
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/lw2-direct-lease"],
        cwd=repo,
        check=True,
    )

    missing = filesystem_writer_lease_action(
        action="acquire", repo=repo, task_id="S2E-LW2", owner="E1",
    )
    assert missing["status"] == "FAIL"
    assert missing["reasons"] == ["TASK_ADMISSION_ID_REQUIRED"]

    wrong = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id="0" * 32,
    )
    assert wrong["status"] == "FAIL"
    assert wrong["reasons"] == ["TASK_ADMISSION_ID_MISMATCH"]

    wrong_task = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E.LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    assert wrong_task["status"] == "FAIL"
    assert wrong_task["reasons"] == ["TASK_ADMISSION_TASK_MISMATCH"]

    wrong_owner = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E2",
        admission_id=admission["admission_id"],
    )
    assert wrong_owner["status"] == "FAIL"
    assert wrong_owner["reasons"] == ["TASK_ADMISSION_OWNER_MISMATCH"]

    other_root = tmp_path / "other-worktree"
    other_root.mkdir()
    other_repo = _clone_evidence_repo(source, other_root)
    wrong_worktree = filesystem_writer_lease_action(
        action="acquire",
        repo=other_repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    assert wrong_worktree["status"] == "FAIL"
    assert wrong_worktree["reasons"] == ["TASK_ADMISSION_MISSING"]

    governed_source = repo / LW2_WRITABLE_PATH
    governed_source.write_text(
        governed_source.read_text(encoding="utf-8") + "\n# lease race\n",
        encoding="utf-8",
    )
    stale = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    assert stale["status"] == "FAIL"
    assert stale["reasons"] == ["TASK_ADMISSION_GENERATION_MISMATCH"]
    lease_store = FileWriterLeaseStore(inspect_worktree(repo).common_dir)
    assert lease_store.read()["leases"] == {}
    assert lease_store.state_path.exists() is False


def test_lw2_lease_lifecycle_is_bound_to_admission_and_generation(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/lw2-write"],
        cwd=repo,
        check=True,
    )
    identity = inspect_worktree(repo)
    lease_store = FileWriterLeaseStore(identity.common_dir)

    for relabelled_task in ("S2E-LW2", "generic-relabelling"):
        bypass = acquire_writer_lease(
            lease_store,
            identity,
            task_id=relabelled_task,
            owner="E1",
        )
        assert bypass["status"] == "FAIL"
        assert bypass["reasons"] == ["TASK_ADMISSION_ID_REQUIRED"]
    relabelled = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="generic-relabelling",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    assert relabelled["status"] == "FAIL"
    assert relabelled["reasons"] == ["TASK_ADMISSION_TASK_MISMATCH"]

    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    assert acquired["status"] == "PASS"
    lease = acquired["lease"]
    assert set(lease) == {
        "lease_id", "task_id", "owner", "worktree", "branch",
        "acquired_at", "expires_at", "admission_id",
        "accepted_generation_digest",
    }
    assert lease["admission_id"] == admission["admission_id"]
    assert lease["accepted_generation_digest"] == canonical_claim_digest(
        admission["admission"]["accepted_generation"]
    )
    for direct in (
        validate_writer_lease(
            lease_store,
            identity,
            task_id="S2E-LW2",
            owner="E1",
            lease_id=lease["lease_id"],
        ),
        renew_writer_lease(
            lease_store,
            identity,
            task_id="S2E-LW2",
            owner="E1",
            lease_id=lease["lease_id"],
        ),
        release_writer_lease(
            lease_store,
            identity,
            task_id="S2E-LW2",
            owner="E1",
            lease_id=lease["lease_id"],
        ),
    ):
        assert direct["status"] == "FAIL"
        assert direct["reasons"] == ["TASK_ADMISSION_ACTION_REQUIRED"]

    missing_status = filesystem_writer_lease_action(
        action="status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=lease["lease_id"],
    )
    assert missing_status["status"] == "FAIL"
    assert missing_status["reasons"] == ["TASK_ADMISSION_ID_REQUIRED"]
    status = filesystem_writer_lease_action(
        action="status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=lease["lease_id"],
        admission_id=admission["admission_id"],
    )
    assert status["status"] == "PASS"

    governed_source = repo / LW2_WRITABLE_PATH
    original = governed_source.read_text(encoding="utf-8")
    governed_source.write_text(original + "\n# leased drift\n", encoding="utf-8")
    for action in ("status", "renew"):
        drifted = filesystem_writer_lease_action(
            action=action,
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            lease_id=lease["lease_id"],
            admission_id=admission["admission_id"],
        )
        assert drifted["status"] == "FAIL"
        assert drifted["reasons"] == ["TASK_ADMISSION_GENERATION_MISMATCH"]
    governed_source.write_text(original, encoding="utf-8")

    terminal = continue_admitted_task(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
        work_status="DONE",
    )
    assert terminal["status"] == "PASS"
    assert terminal["admission"]["state"] == "TERMINAL"
    terminal_status = filesystem_writer_lease_action(
        action="status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=lease["lease_id"],
        admission_id=admission["admission_id"],
    )
    assert terminal_status["status"] == "FAIL"
    assert terminal_status["reasons"] == ["TASK_ADMISSION_TERMINAL"]

    released_admission = release_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    assert released_admission["status"] == "PASS"
    released_renew = filesystem_writer_lease_action(
        action="renew",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=lease["lease_id"],
        admission_id=admission["admission_id"],
    )
    assert released_renew["status"] == "FAIL"
    assert released_renew["reasons"] == ["TASK_ADMISSION_MISSING"]
    no_new_authority = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    assert no_new_authority["status"] == "FAIL"
    assert no_new_authority["reasons"] == ["TASK_ADMISSION_MISSING"]
    released_lease = filesystem_writer_lease_action(
        action="release",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=lease["lease_id"],
        admission_id=admission["admission_id"],
    )
    assert released_lease["status"] == "PASS"
    assert lease_store.read()["leases"] == {}


def test_lw2_publication_status_authorizes_only_the_admitted_clean_feature_commit(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/lw2-publication"],
        cwd=repo,
        check=True,
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    lease = acquired["lease"]
    governed_source = repo / LW2_WRITABLE_PATH
    governed_source.write_text(
        governed_source.read_text(encoding="utf-8")
        + "\n# admitted publication commit\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "--", LW2_WRITABLE_PATH], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "admitted LW2 feature"],
        cwd=repo,
        check=True,
    )

    common_dir = inspect_worktree(repo).common_dir
    admission_store = FileTaskAdmissionStore(common_dir)
    lease_store = FileWriterLeaseStore(common_dir)
    persisted_before = {
        "admission": admission_store.state_path.read_bytes(),
        "lease": lease_store.state_path.read_bytes(),
        "binding": lease_store.binding_path.read_bytes(),
    }
    for action in ("status", "renew"):
        generic = filesystem_writer_lease_action(
            action=action,
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            lease_id=lease["lease_id"],
            admission_id=admission["admission_id"],
        )
        assert generic["status"] == "FAIL"
        assert generic["reasons"] == ["TASK_ADMISSION_GENERATION_MISMATCH"]

    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=lease["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "PASS"
    assert publication["action"] == "publication-status"
    assert publication["admission_scope"] == {
        "task_contract_digest": admission["admission"]["task_contract_digest"],
        "dirty_scope": list(contract["dirty_scope"]),
        "lw2_selected": True,
    }
    assert publication["publication_status"]["schema_version"] == (
        "lw2_writer_publication_status_v1"
    )
    assert publication["publication_status"]["accepted_base"]["head"] == (
        admission["admission"]["accepted_generation"]["source_head"]
    )
    assert publication["publication_status"]["feature"]["head"] == _git_value(
        repo, "HEAD"
    )
    assert publication["publication_boundary"]["publication_source_sha"] == (
        _git_value(repo, "HEAD")
    )
    assert publication["publication_boundary"]["push_refspec"] == (
        f"{_git_value(repo, 'HEAD')}:refs/heads/agent/lw2-publication"
    )
    assert publication["publication_status"]["ordered_commits"] == [
        _git_value(repo, "HEAD")
    ]
    assert publication["publication_status"]["touched_paths"] == [
        LW2_WRITABLE_PATH
    ]
    feature_head = _git_value(repo, "HEAD")
    base_head = admission["admission"]["accepted_generation"]["source_head"]
    feature_tree = _git_value(repo, "HEAD^{tree}")
    commit_paths = [{
        "commit": feature_head,
        "parent": base_head,
        "tree": feature_tree,
        "paths": [LW2_WRITABLE_PATH],
    }]
    patch = subprocess.run(
        [
            "git", "diff-tree", "-r", "--no-commit-id", "--no-renames",
            "--no-ext-diff", "--no-textconv", "--binary", "--full-index",
            "-p", base_head, feature_head, "--",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    patch_records = [{
        "commit": feature_head,
        "binary_patch_digest": "sha256:" + hashlib.sha256(patch).hexdigest(),
    }]
    empty_digest = _digest([])
    native_graph = {
        "schema_version": "lw2_native_git_graph_v1",
        "read_mode": "git_--no-replace-objects",
        "git_replace_ref_base": "ABSENT",
        "replace_namespace": "refs/replace/",
        "replace_ref_count": 0,
        "replace_refs_digest": empty_digest,
        "grafts": "ABSENT",
        "grafts_digest": empty_digest,
    }
    feature_generation = capture_task_admission_generation(repo, contract)
    assert publication["publication_status"]["native_graph"] == native_graph
    assert publication["publication_status"]["native_graph_digest"] == _digest(
        native_graph
    )
    assert publication["publication_status"]["ordered_commit_path_digest"] == (
        _digest(commit_paths)
    )
    assert publication["publication_status"]["binary_patch_digest"] == _digest(
        {
            "native_graph_digest": _digest(native_graph),
            "patch_records": patch_records,
        }
    )
    assert publication["publication_status"]["feature"][
        "generation_digest"
    ] == _digest(feature_generation)
    assert persisted_before == {
        "admission": admission_store.state_path.read_bytes(),
        "lease": lease_store.state_path.read_bytes(),
        "binding": lease_store.binding_path.read_bytes(),
    }


@pytest.mark.parametrize("authority_race", ["admission-terminalize", "lease-release"])
def test_publication_final_observation_holds_both_authority_locks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
    authority_race: str,
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch=f"agent/lw2-publication-{authority_race}",
        marker=f"admitted {authority_race} boundary",
    )
    identity = inspect_worktree(repo)
    lock_path = (
        FileTaskAdmissionStore(identity.common_dir).lock_path
        if authority_race == "admission-terminalize"
        else FileWriterLeaseStore(identity.common_dir).lock_path
    )
    base = _git_value(repo, "refs/remotes/origin/main")
    feature = _git_value(repo, "HEAD")
    observed_locked = False
    events: list[str] = []
    original_snapshot = capture_module.capture_native_protected_snapshot
    def observed_snapshot(*args, **kwargs):
        snapshot = original_snapshot(*args, **kwargs)
        events.append("snapshot")
        return snapshot
    original_clock = writer_lease_module._utc_now
    def observed_clock():
        events.append("clock")
        return original_clock()
    def locked_remote_head(_repo: Path, _url: str, ref: str) -> str | None:
        nonlocal observed_locked
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import fcntl,sys; f=open(sys.argv[1], 'a+'); "
                    "\ntry: fcntl.flock(f.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)"
                    "\nexcept BlockingIOError: raise SystemExit(73)"
                    "\nraise SystemExit(0)"
                ),
                str(lock_path),
            ],
            check=False,
        )
        assert probe.returncode == 73
        observed_locked = True
        events.append(ref)
        return base if ref == LW2_DESTINATION_REF else feature

    monkeypatch.setattr(
        capture_module, "capture_native_protected_snapshot", observed_snapshot
    )
    monkeypatch.setattr(writer_lease_module, "_utc_now", observed_clock)
    monkeypatch.setattr(
        writer_lease_module, "_canonical_remote_head", locked_remote_head
    )
    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
        publication_phase="post-push",
        publication_expected_branch=identity.branch,
        publication_expected_head=feature,
    )

    assert publication["status"] == "PASS"
    assert observed_locked is True
    final_snapshot = max(index for index, event in enumerate(events) if event == "snapshot")
    assert events[final_snapshot + 1:] == [LW2_DESTINATION_REF, f"refs/heads/{identity.branch}", "clock"]


@pytest.mark.parametrize("feature_race", ["head", "worktree"])
def test_publication_finalization_rejects_feature_mutation_after_status_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
    feature_race: str,
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch=f"agent/lw2-publication-final-{feature_race}-race",
        marker=f"admitted final {feature_race} race",
    )
    expected_head = _git_value(repo, "HEAD")
    mutated = False
    original_snapshot = capture_module.capture_native_protected_snapshot

    def racing_snapshot(*args, **kwargs):
        nonlocal mutated
        snapshot = original_snapshot(*args, **kwargs)
        if not mutated:
            mutated = True
            if feature_race == "head":
                subprocess.run(
                    ["git", "commit", "-q", "--allow-empty", "-m", "race head"],
                    cwd=repo,
                    check=True,
                )
            else:
                governed = repo / LW2_WRITABLE_PATH
                governed.write_text(
                    governed.read_text(encoding="utf-8") + "\n# race bytes\n",
                    encoding="utf-8",
                )
        return snapshot

    monkeypatch.setattr(capture_module, "capture_native_protected_snapshot", racing_snapshot)
    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
        publication_phase="publish",
        publication_expected_branch=inspect_worktree(repo).branch,
        publication_expected_head=expected_head,
    )

    assert publication["status"] == "FAIL"
    assert "PUBLICATION_FINAL_FEATURE_DRIFT" in publication["reasons"]
    assert "publication_status" not in publication


def test_lw2_publication_status_rejects_origin_pushurl_redirection(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch="agent/lw2-publication-pushurl",
        marker="admitted pushurl feature",
    )
    subprocess.run(
        [
            "git", "config", "--add", "remote.origin.pushurl",
            "https://example.invalid/redirect.git",
        ],
        cwd=repo,
        check=True,
    )

    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert publication["reasons"] == [
        "LW2_PUBLICATION_ORIGIN_PUSH_URL_MISMATCH"
    ]


@pytest.mark.parametrize(
    ("config_key", "expected_reason"),
    [
        ("remote.origin.url", "LW2_PUBLICATION_ORIGIN_FETCH_URL_MISMATCH"),
        ("remote.origin.pushurl", "LW2_PUBLICATION_ORIGIN_PUSH_URL_MISMATCH"),
    ],
)
def test_lw2_publication_status_rejects_duplicate_origin_urls(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
    config_key: str,
    expected_reason: str,
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch=f"agent/lw2-publication-{config_key.rsplit('.', 1)[-1]}",
        marker=f"admitted duplicate {config_key} feature",
    )
    for _ in range(2 if config_key.endswith("pushurl") else 1):
        subprocess.run(
            ["git", "config", "--add", config_key, LW2_REPOSITORY_URL],
            cwd=repo,
            check=True,
        )

    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert expected_reason in publication["reasons"]


def test_lw2_publication_status_rejects_final_origin_url_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch="agent/lw2-publication-url-race",
        marker="admitted URL race feature",
    )
    original = capture_module.capture_native_protected_snapshot

    def change_after_final_snapshot(repository: Path, **kwargs):
        snapshot = original(repository, **kwargs)
        subprocess.run(
            [
                "git", "config", "remote.origin.pushurl",
                "https://example.invalid/raced.git",
            ],
            cwd=repository,
            check=True,
        )
        return snapshot

    monkeypatch.setattr(capture_module, "capture_native_protected_snapshot", change_after_final_snapshot)
    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert "FINAL_ORIGIN_URL_MISMATCH" in publication["reasons"]
    assert "LW2_PUBLICATION_FINAL_ORIGIN_URL_DRIFT" in publication["reasons"]


def test_lw2_publication_status_rejects_final_local_main_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch="agent/lw2-publication-local-main-race",
        marker="admitted local main race feature",
    )
    feature_head = _git_output(repo, "rev-parse", "HEAD")
    original = capture_module.capture_native_protected_snapshot

    def change_after_final_snapshot(repository: Path, **kwargs):
        snapshot = original(repository, **kwargs)
        subprocess.run(
            [
                "git", "update-ref", "refs/remotes/origin/main", feature_head,
            ],
            cwd=repository,
            check=True,
        )
        return snapshot

    monkeypatch.setattr(capture_module, "capture_native_protected_snapshot", change_after_final_snapshot)
    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert publication["reasons"] == ["FINAL_TRUE_ORIGIN_MAIN_DRIFT"]


def test_lw2_admission_and_publication_never_execute_configured_textconv(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    sentinel = tmp_path / "writer-textconv-executed"
    attributes = Path(_git_output(repo, "rev-parse", "--git-path", "info/attributes"))
    if not attributes.is_absolute():
        attributes = repo / attributes
    attributes.parent.mkdir(parents=True, exist_ok=True)
    attributes.write_text(
        f"{LW2_WRITABLE_PATH} diff=sentinel\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "config", "diff.sentinel.textconv", f"touch {sentinel}"],
        cwd=repo,
        check=True,
    )
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    assert not sentinel.exists()
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/lw2-publication-textconv"],
        cwd=repo,
        check=True,
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    governed_source = repo / LW2_WRITABLE_PATH
    governed_source.write_text(
        governed_source.read_text(encoding="utf-8")
        + "\n# admitted textconv feature\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "--", LW2_WRITABLE_PATH], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "admitted textconv feature"],
        cwd=repo,
        check=True,
    )
    governed_source.write_text(
        governed_source.read_text(encoding="utf-8") + "\n# dirty evidence\n",
        encoding="utf-8",
    )

    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert not sentinel.exists()


@pytest.mark.parametrize("index_flag", ["--assume-unchanged", "--skip-worktree"])
def test_lw2_publication_status_rejects_hidden_protected_bytes(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
    index_flag: str,
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch=f"agent/lw2-publication-{index_flag.removeprefix('--')}",
        marker=f"admitted {index_flag} feature",
    )
    subprocess.run(
        ["git", "update-index", index_flag, "--", LW2_WRITABLE_PATH],
        cwd=repo,
        check=True,
    )
    governed_source = repo / LW2_WRITABLE_PATH
    governed_source.write_text(
        governed_source.read_text(encoding="utf-8")
        + "\n# hidden protected mutation\n",
        encoding="utf-8",
    )
    assert _git_output(repo, "status", "--porcelain=v1") == ""

    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert "LW2_PUBLICATION_FEATURE_GENERATION_MISMATCH" in publication[
        "reasons"
    ]
    assert not any("UNAVAILABLE" in reason for reason in publication["reasons"])


def test_lw2_publication_status_final_recapture_rejects_generation_capture_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/lw2-publication-race"],
        cwd=repo,
        check=True,
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    governed_source = repo / LW2_WRITABLE_PATH
    governed_source.write_text(
        governed_source.read_text(encoding="utf-8")
        + "\n# admitted publication race commit\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "--", LW2_WRITABLE_PATH], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "admitted LW2 race feature"],
        cwd=repo,
        check=True,
    )

    original_capture = writer_lease_module._capture_lw2_publication_generation
    calls = 0

    def mutate_after_second_capture(
        repository: Path,
        task_contract: dict[str, object],
        *,
        canonical_claim_digest,
    ) -> dict[str, object]:
        nonlocal calls
        generation = original_capture(
            repository,
            task_contract,
            canonical_claim_digest=canonical_claim_digest,
        )
        calls += 1
        if calls == 1:
            subprocess.run(
                [
                    "git", "update-index", "--assume-unchanged", "--",
                    LW2_WRITABLE_PATH,
                ],
                cwd=repository,
                check=True,
            )
            governed_source.write_text(
                governed_source.read_text(encoding="utf-8")
                + "\n# raced after generation capture\n",
                encoding="utf-8",
            )
        return generation

    monkeypatch.setattr(
        writer_lease_module,
        "_capture_lw2_publication_generation",
        mutate_after_second_capture,
    )
    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert publication["reasons"] == [
        "LW2_PUBLICATION_FINAL_GENERATION_MISMATCH"
    ]
    assert calls == 1


def test_lw2_publication_status_rejects_expiry_during_evidence_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch="agent/lw2-publication-mid-evaluation-expiry",
        marker="admitted mid-evaluation expiry baseline",
    )
    identity = inspect_worktree(repo)
    admission_store = FileTaskAdmissionStore(identity.common_dir)
    lease_store = FileWriterLeaseStore(identity.common_dir)
    persisted_before = {
        "admission": admission_store.state_path.read_bytes(),
        "lease": lease_store.state_path.read_bytes(),
        "binding": lease_store.binding_path.read_bytes(),
    }
    expires_at = datetime.fromisoformat(
        acquired["lease"]["expires_at"].replace("Z", "+00:00")
    )
    trusted_times = iter([
        expires_at - timedelta(microseconds=1),
        expires_at,
    ])
    monkeypatch.setattr(
        writer_lease_module, "_utc_now", lambda: next(trusted_times)
    )

    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert publication["reasons"] == ["WRITER_LEASE_EXPIRED"]
    assert publication["admission_scope"] is None
    assert "publication_status" not in publication
    assert persisted_before == {
        "admission": admission_store.state_path.read_bytes(),
        "lease": lease_store.state_path.read_bytes(),
        "binding": lease_store.binding_path.read_bytes(),
    }


def test_publication_status_denies_caller_backdating_for_ordinary_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _linked_main_evidence_repo(ROOT, tmp_path)
    contract = task_contract_projection(route_task(
        {
            **_ordinary_route_facts(),
            "baseline": capture_repository_baseline(repo),
        },
        repo=repo,
    )["task_facts"])
    admission = acquire_task_admission(
        repo=repo,
        task_id="ORDINARY-PUBLICATION-EXPIRY",
        owner="E1",
        task_contract=contract,
    )
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/ordinary-publication-expiry"],
        cwd=repo,
        check=True,
    )
    lease_start = datetime(2030, 1, 1, tzinfo=timezone.utc)
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="ORDINARY-PUBLICATION-EXPIRY",
        owner="E1",
        admission_id=admission["admission_id"],
        now=lease_start,
    )
    expires_at = datetime.fromisoformat(
        acquired["lease"]["expires_at"].replace("Z", "+00:00")
    )
    identity = inspect_worktree(repo)
    admission_store = FileTaskAdmissionStore(identity.common_dir)
    lease_store = FileWriterLeaseStore(identity.common_dir)
    persisted_before = {
        "admission": admission_store.state_path.read_bytes(),
        "lease": lease_store.state_path.read_bytes(),
        "binding": lease_store.binding_path.read_bytes(),
    }
    monkeypatch.setattr(writer_lease_module, "_utc_now", lambda: expires_at)

    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="ORDINARY-PUBLICATION-EXPIRY",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
        now=lease_start,
    )

    assert publication["status"] == "FAIL"
    assert publication["reasons"] == ["WRITER_LEASE_EXPIRED"]
    assert publication["admission_scope"] is None
    assert "publication_status" not in publication
    assert persisted_before == {
        "admission": admission_store.state_path.read_bytes(),
        "lease": lease_store.state_path.read_bytes(),
        "binding": lease_store.binding_path.read_bytes(),
    }


def test_publication_status_passes_only_when_both_trusted_times_are_unexpired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _linked_main_evidence_repo(ROOT, tmp_path)
    contract = task_contract_projection(route_task(
        {
            **_ordinary_route_facts(),
            "baseline": capture_repository_baseline(repo),
        },
        repo=repo,
    )["task_facts"])
    admission = acquire_task_admission(
        repo=repo,
        task_id="ORDINARY-PUBLICATION-STRICTLY-UNEXPIRED",
        owner="E1",
        task_contract=contract,
    )
    subprocess.run(
        [
            "git", "switch", "-q", "-c",
            "agent/ordinary-publication-strictly-unexpired",
        ],
        cwd=repo,
        check=True,
    )
    lease_start = datetime(2031, 1, 1, tzinfo=timezone.utc)
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="ORDINARY-PUBLICATION-STRICTLY-UNEXPIRED",
        owner="E1",
        admission_id=admission["admission_id"],
        now=lease_start,
    )
    expires_at = datetime.fromisoformat(
        acquired["lease"]["expires_at"].replace("Z", "+00:00")
    )
    expected_times = [
        expires_at - timedelta(microseconds=2),
        expires_at - timedelta(microseconds=1),
    ]
    trusted_times = iter(expected_times)
    observed_times: list[datetime] = []

    def trusted_now() -> datetime:
        observed = next(trusted_times)
        observed_times.append(observed)
        return observed

    monkeypatch.setattr(writer_lease_module, "_utc_now", trusted_now)
    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="ORDINARY-PUBLICATION-STRICTLY-UNEXPIRED",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
        now=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )

    assert publication["status"] == "PASS"
    assert publication["reasons"] == []
    assert publication["admission_scope"] == {
        "task_contract_digest": admission["admission"]["task_contract_digest"],
        "dirty_scope": list(contract["dirty_scope"]),
        "lw2_selected": False,
    }
    assert "publication_status" not in publication
    assert observed_times == expected_times


def test_lw2_publication_status_rejects_git_replace_graph_projection(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/lw2-publication-replace"],
        cwd=repo,
        check=True,
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    base_head = admission["admission"]["accepted_generation"]["source_head"]
    outside = "outside-publication-scope.txt"
    (repo / outside).write_text("native outside path\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", outside], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "native outside feature"],
        cwd=repo,
        check=True,
    )
    native_feature = _git_value(repo, "HEAD")
    subprocess.run(
        ["git", "reset", "--hard", base_head],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    governed_source = repo / LW2_WRITABLE_PATH
    governed_source.write_text(
        governed_source.read_text(encoding="utf-8")
        + "\n# projected admitted feature\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "--", LW2_WRITABLE_PATH], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "projected admitted feature"],
        cwd=repo,
        check=True,
    )
    legal_projection = _git_value(repo, "HEAD")
    subprocess.run(
        ["git", "replace", native_feature, legal_projection],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "reset", "--hard", native_feature],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    ordinary_paths = subprocess.run(
        [
            "git", "diff-tree", "-r", "--no-commit-id", "--no-renames",
            "--name-only", base_head, native_feature, "--",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    native_paths = subprocess.run(
        [
            "git", "--no-replace-objects", "diff-tree", "-r",
            "--no-commit-id", "--no-renames", "--name-only", base_head,
            native_feature, "--",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert ordinary_paths == [LW2_WRITABLE_PATH]
    assert native_paths == [outside]
    assert subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""

    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert publication["reasons"] == [
        "LW2_PUBLICATION_GRAPH_PROJECTION_PRESENT"
    ]

    subprocess.run(
        ["git", "pack-refs", "--all", "--prune"], cwd=repo, check=True
    )
    assert subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/replace/"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines() == [f"refs/replace/{native_feature}"]
    replace_namespace = inspect_worktree(repo).common_dir / "refs" / "replace"
    assert not replace_namespace.exists() or not any(replace_namespace.iterdir())
    packed_publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )
    assert packed_publication["status"] == "FAIL"
    assert packed_publication["reasons"] == [
        "LW2_PUBLICATION_GRAPH_PROJECTION_PRESENT"
    ]


def test_lw2_publication_status_final_native_graph_recapture_is_fenced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch="agent/lw2-publication-graph-race",
        marker="admitted graph-race baseline",
    )
    grafts = inspect_worktree(repo).common_dir / "info" / "grafts"
    original_capture = writer_lease_module._capture_native_graph_safety
    calls = 0

    def inject_projection_before_final_capture(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            grafts.write_bytes(b"")
        return original_capture(**kwargs)

    monkeypatch.setattr(
        writer_lease_module,
        "_capture_native_graph_safety",
        inject_projection_before_final_capture,
    )
    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert calls == 2
    assert publication["status"] == "FAIL"
    assert publication["reasons"] == [
        "LW2_PUBLICATION_GRAPH_PROJECTION_PRESENT"
    ]


def test_lw2_publication_status_rejects_every_ambient_graph_projection_node(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch="agent/lw2-publication-graph-nodes",
        marker="admitted graph-node baseline",
    )
    common_dir = inspect_worktree(repo).common_dir

    def assert_projection_rejected() -> None:
        publication = filesystem_writer_lease_action(
            action="publication-status",
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            lease_id=acquired["lease"]["lease_id"],
            admission_id=admission["admission_id"],
        )
        assert publication["status"] == "FAIL"
        assert publication["reasons"] == [
            "LW2_PUBLICATION_GRAPH_PROJECTION_PRESENT"
        ]

    monkeypatch.setenv("GIT_REPLACE_REF_BASE", "refs/alternate-replace/")
    assert_projection_rejected()
    monkeypatch.delenv("GIT_REPLACE_REF_BASE")

    grafts = common_dir / "info" / "grafts"
    grafts.write_bytes(b"")
    assert_projection_rejected()
    grafts.unlink()

    graft_target = tmp_path / "graft-target"
    graft_target.write_text("", encoding="utf-8")
    grafts.symlink_to(graft_target)
    assert_projection_rejected()
    grafts.unlink()

    grafts.mkdir()
    assert_projection_rejected()
    grafts.rmdir()

    grafts.write_text("", encoding="utf-8")
    grafts.chmod(0)
    assert_projection_rejected()
    grafts.chmod(0o600)
    grafts.unlink()

    replace_namespace = common_dir / "refs" / "replace"
    replace_target = tmp_path / "replace-target"
    replace_target.mkdir()
    replace_namespace.symlink_to(replace_target, target_is_directory=True)
    assert_projection_rejected()
    replace_namespace.unlink()

    replace_namespace.write_text("not a directory\n", encoding="utf-8")
    assert_projection_rejected()
    replace_namespace.unlink()


def test_git_loop_guard_uses_publication_status_only_for_publish_phases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/lw2-publication-guard"],
        cwd=repo,
        check=True,
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    governed_source = repo / LW2_WRITABLE_PATH
    governed_source.write_text(
        governed_source.read_text(encoding="utf-8")
        + "\n# admitted guarded publication commit\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "--", LW2_WRITABLE_PATH], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "admitted guarded LW2 feature"],
        cwd=repo,
        check=True,
    )
    feature_head = _git_value(repo, "HEAD")
    base_head = admission["admission"]["accepted_generation"]["source_head"]
    monkeypatch.setattr(
        git_guard,
        "_true_remote_head",
        lambda _repo, ref, remote="origin": base_head
        if ref == "refs/heads/main"
        else feature_head,
    )
    authority = {
        "writer_task_id": "S2E-LW2",
        "writer_owner": "E1",
        "writer_lease_id": acquired["lease"]["lease_id"],
        "writer_admission_id": admission["admission_id"],
    }

    start = git_guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/lw2-publication-guard",
        expected_head=feature_head,
        **authority,
    )
    publish = git_guard.evaluate(
        repo,
        phase="publish",
        expected_branch="agent/lw2-publication-guard",
        expected_head=feature_head,
        **authority,
    )
    checkpoint = git_guard.evaluate(
        repo,
        phase="checkpoint",
        expected_branch="agent/lw2-publication-guard",
        expected_head=feature_head,
        allow_paths=contract["dirty_scope"],
        **authority,
    )
    subprocess.run(
        [
            "git", "update-ref",
            "refs/remotes/origin/agent/lw2-publication-guard",
            feature_head,
        ],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        [
            "git", "branch", "--set-upstream-to",
            "origin/agent/lw2-publication-guard",
            "agent/lw2-publication-guard",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    post_push = git_guard.evaluate(
        repo,
        phase="post-push",
        expected_branch="agent/lw2-publication-guard",
        expected_head=feature_head,
        **authority,
    )
    expires_at = datetime.fromisoformat(
        acquired["lease"]["expires_at"].replace("Z", "+00:00")
    )
    trusted_times = iter([
        expires_at - timedelta(microseconds=1),
        expires_at,
    ])
    monkeypatch.setattr(
        writer_lease_module, "_utc_now", lambda: next(trusted_times)
    )
    expired_publish = git_guard.evaluate(
        repo,
        phase="publish",
        expected_branch="agent/lw2-publication-guard",
        expected_head=feature_head,
        **authority,
    )

    assert start["status"] == "FAIL"
    assert "TASK_ADMISSION_GENERATION_MISMATCH" in start["reasons"]
    assert checkpoint["status"] == "FAIL"
    assert "TASK_ADMISSION_GENERATION_MISMATCH" in checkpoint["reasons"]
    assert publish["status"] == "PASS"
    assert publish["state"]["writer_lease"]["status"] == "PASS"
    assert publish["state"]["writer_publication_status"]["schema_version"] == (
        "lw2_writer_publication_status_v1"
    )
    assert post_push["status"] == "PASS"
    assert post_push["state"]["writer_publication_status"] == publish["state"][
        "writer_publication_status"
    ]
    assert expired_publish["status"] == "FAIL"
    assert expired_publish["reasons"] == ["WRITER_LEASE_EXPIRED"]
    assert expired_publish["state"]["writer_lease"]["status"] == "FAIL"


@pytest.mark.parametrize(
    ("mutation", "expected_reasons"),
    [
        (
            "tracked",
            ["LW2_PUBLICATION_DIRTY_WORKTREE"],
        ),
        (
            "staged",
            [
                "LW2_PUBLICATION_STAGED_CHANGES",
                "LW2_PUBLICATION_DIRTY_WORKTREE",
                "LW2_PUBLICATION_FEATURE_GENERATION_MISMATCH",
            ],
        ),
        ("untracked", ["LW2_PUBLICATION_DIRTY_WORKTREE"]),
    ],
)
def test_lw2_publication_status_rejects_any_uncommitted_feature_bytes(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
    mutation: str,
    expected_reasons: list[str],
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch=f"agent/lw2-publication-{mutation}",
        marker=f"admitted {mutation} baseline",
    )
    if mutation in {"tracked", "staged"}:
        governed_source = repo / LW2_WRITABLE_PATH
        governed_source.write_text(
            governed_source.read_text(encoding="utf-8")
            + f"\n# {mutation} publication bytes\n",
            encoding="utf-8",
        )
        if mutation == "staged":
            subprocess.run(
                ["git", "add", "--", LW2_WRITABLE_PATH], cwd=repo, check=True
            )
    else:
        (repo / "publication-untracked.txt").write_text(
            "untracked\n", encoding="utf-8"
        )

    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert publication["reasons"] == expected_reasons


@pytest.mark.parametrize(
    ("topology", "required_reasons"),
    [
        (
            "origin-remote",
            [
                "LW2_PUBLICATION_ORIGIN_FETCH_URL_MISMATCH",
                "LW2_PUBLICATION_ORIGIN_PUSH_URL_MISMATCH",
            ],
        ),
        ("origin-drift", ["LW2_PUBLICATION_ORIGIN_MAIN_DRIFT"]),
        ("sibling", ["LW2_PUBLICATION_BASE_NOT_ANCESTOR"]),
        ("merge", ["LW2_PUBLICATION_NONLINEAR_HISTORY"]),
    ],
)
def test_lw2_publication_status_rejects_base_or_linear_history_drift(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
    topology: str,
    required_reasons: list[str],
) -> None:
    source, contract = real_lw2_contract
    branch = f"agent/lw2-publication-{topology}"
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch=branch,
        marker=f"admitted {topology} feature",
    )
    base_head = admission["admission"]["accepted_generation"]["source_head"]
    if topology == "origin-remote":
        subprocess.run(
            ["git", "remote", "set-url", "origin", "https://example.invalid/repo.git"],
            cwd=repo,
            check=True,
        )
    elif topology == "origin-drift":
        subprocess.run(
            [
                "git", "update-ref", "refs/remotes/origin/main",
                _git_value(repo, "HEAD"),
            ],
            cwd=repo,
            check=True,
        )
    elif topology == "sibling":
        subprocess.run(
            ["git", "reset", "--hard", f"{base_head}^"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        governed_source = repo / LW2_WRITABLE_PATH
        governed_source.write_text(
            governed_source.read_text(encoding="utf-8")
            + "\n# sibling feature\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", "--", LW2_WRITABLE_PATH], cwd=repo, check=True
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "sibling feature"],
            cwd=repo,
            check=True,
        )
    else:
        subprocess.run(
            ["git", "switch", "-q", "-c", "lw2-empty-side", base_head],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", "empty side"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "switch", "-q", branch], cwd=repo, check=True
        )
        subprocess.run(
            ["git", "merge", "-q", "--no-ff", "lw2-empty-side", "-m", "merge side"],
            cwd=repo,
            check=True,
        )

    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert set(required_reasons).issubset(publication["reasons"])


@pytest.mark.parametrize("escape", ["commit", "commit-then-revert", "rename"])
def test_lw2_publication_status_checks_every_commit_path_without_renames(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
    escape: str,
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch=f"agent/lw2-publication-{escape}",
        marker=f"admitted {escape} baseline",
    )
    outside = "outside-publication-scope.txt"
    if escape == "rename":
        subprocess.run(
            ["git", "mv", "--", LW2_WRITABLE_PATH, outside],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "rename outside admitted scope"],
            cwd=repo,
            check=True,
        )
    else:
        (repo / outside).write_text("outside\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", outside], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "commit outside admitted scope"],
            cwd=repo,
            check=True,
        )
        if escape == "commit-then-revert":
            (repo / outside).unlink()
            subprocess.run(
                ["git", "add", "--", outside], cwd=repo, check=True
            )
            subprocess.run(
                ["git", "commit", "-q", "-m", "revert outside path"],
                cwd=repo,
                check=True,
            )

    publication = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert publication["status"] == "FAIL"
    assert (
        "LW2_PUBLICATION_COMMITTED_PATH_OUTSIDE_ADMITTED_SCOPE"
        in publication["reasons"]
    )
    if escape == "rename":
        assert "LW2_PUBLICATION_FEATURE_GENERATION_MISMATCH" in publication[
            "reasons"
        ]
        assert not any("UNAVAILABLE" in reason for reason in publication["reasons"])


def test_lw2_publication_status_requires_exact_unexpired_fencing_tuple(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo, admission, acquired = _admitted_lw2_publication_feature(
        source=source,
        contract=contract,
        tmp_path=tmp_path,
        branch="agent/lw2-publication-fencing",
        marker="admitted fencing feature",
    )
    base = {
        "action": "publication-status",
        "repo": repo,
        "task_id": "S2E-LW2",
        "owner": "E1",
        "lease_id": acquired["lease"]["lease_id"],
        "admission_id": admission["admission_id"],
    }
    cases = (
        ({**base, "admission_id": "0" * 32}, "TASK_ADMISSION_ID_MISMATCH"),
        ({**base, "lease_id": "0" * 32}, "WRITER_LEASE_ID_MISMATCH"),
        ({**base, "owner": "E1a"}, "TASK_ADMISSION_OWNER_MISMATCH"),
    )

    for arguments, reason in cases:
        result = filesystem_writer_lease_action(**arguments)
        assert result["status"] == "FAIL"
        assert reason in result["reasons"]


def test_lw2_publication_status_requires_an_active_admission(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/lw2-publication-terminal"],
        cwd=repo,
        check=True,
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )
    terminal = continue_admitted_task(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
        work_status="DONE",
    )
    assert terminal["admission"]["state"] == "TERMINAL"

    result = filesystem_writer_lease_action(
        action="publication-status",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=acquired["lease"]["lease_id"],
        admission_id=admission["admission_id"],
    )

    assert result["status"] == "FAIL"
    assert result["reasons"] == ["TASK_ADMISSION_TERMINAL"]


def test_git_loop_guard_accepts_exact_admission_bound_lw2_lease(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/lw2-guard"],
        cwd=repo,
        check=True,
    )
    lease = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )["lease"]

    result = git_guard.evaluate(
        repo,
        phase="start",
        expected_branch="agent/lw2-guard",
        expected_head=_git_value(repo, "HEAD"),
        writer_task_id="S2E-LW2",
        writer_owner="E1",
        writer_lease_id=lease["lease_id"],
        writer_admission_id=admission["admission_id"],
    )

    assert result["status"] == "PASS"
    assert result["state"]["writer_lease"]["status"] == "PASS"


def test_lw2_drift_requires_release_readmit_and_fresh_lease_before_checkpoint(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    first_admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/lw2-readmit"],
        cwd=repo,
        check=True,
    )
    first_lease = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=first_admission["admission_id"],
    )["lease"]
    governed_source = repo / LW2_WRITABLE_PATH
    governed_source.write_text(
        governed_source.read_text(encoding="utf-8") + "\n# readmit lifecycle\n",
        encoding="utf-8",
    )
    for action in ("status", "renew"):
        stale = filesystem_writer_lease_action(
            action=action,
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            lease_id=first_lease["lease_id"],
            admission_id=first_admission["admission_id"],
        )
        assert stale["status"] == "FAIL"
        assert stale["reasons"] == ["TASK_ADMISSION_GENERATION_MISMATCH"]
    assert filesystem_writer_lease_action(
        action="release",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        lease_id=first_lease["lease_id"],
        admission_id=first_admission["admission_id"],
    )["status"] == "PASS"
    assert release_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=first_admission["admission_id"],
    )["status"] == "PASS"

    subprocess.run(["git", "switch", "-q", "main"], cwd=repo, check=True)
    fresh_claim_inputs, fresh_claim_payloads = _real_claims(repo)
    fresh_routed = route_task(
        _route_facts(repo, fresh_claim_inputs, fresh_claim_payloads),
        repo=repo,
        external_evidence_verifier=_strict_external_verifier(
            fresh_claim_payloads
        ),
    )
    fresh_contract = task_contract_projection(fresh_routed["task_facts"])
    fresh_admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(fresh_contract),
        external_evidence_verifier=_strict_external_verifier(
            fresh_contract["claim_payloads"]
        ),
    )
    subprocess.run(
        ["git", "switch", "-q", "agent/lw2-readmit"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "add", "--", LW2_WRITABLE_PATH], cwd=repo, check=True
    )
    staged = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=fresh_admission["admission_id"],
    )
    assert staged["status"] == "FAIL"
    assert staged["reasons"] == ["PREEXISTING_STAGED_CHANGES"]
    subprocess.run(
        ["git", "restore", "--staged", "--", LW2_WRITABLE_PATH],
        cwd=repo,
        check=True,
    )
    outside = repo / "outside-admitted-scope.txt"
    outside.write_text("outside\n", encoding="utf-8")
    out_of_scope = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=fresh_admission["admission_id"],
    )
    assert out_of_scope["status"] == "FAIL"
    assert out_of_scope["reasons"] == ["DIRTY_PATH_OUTSIDE_ADMITTED_SCOPE"]
    outside.unlink()
    fresh_lease = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=fresh_admission["admission_id"],
    )
    assert fresh_lease["status"] == "PASS"
    assert fresh_lease["lease"]["admission_id"] == fresh_admission["admission_id"]

    checkpoint = git_guard.evaluate(
        repo,
        phase="checkpoint",
        expected_branch="agent/lw2-readmit",
        expected_head=_git_value(repo, "HEAD"),
        writer_task_id="S2E-LW2",
        writer_owner="E1",
        writer_lease_id=fresh_lease["lease"]["lease_id"],
        writer_admission_id=fresh_admission["admission_id"],
        allow_paths=[LW2_WRITABLE_PATH],
    )
    assert checkpoint["status"] == "PASS"
    assert checkpoint["state"]["dirty_paths"] == [LW2_WRITABLE_PATH]


def test_lw2_admission_cannot_hide_rename_source_from_protected_scope(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, _ = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    rename_source = "rename-source.txt"
    admitted_destination = (
        "helper_scripts/maintenance_scripts/"
        "agent_governance_s2_5_rename_destination.py"
    )
    (repo / rename_source).write_text("rename source bytes\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "--", rename_source], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "add rename source"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "diff.renames", "true"], cwd=repo, check=True
    )
    (repo / rename_source).rename(repo / admitted_destination)
    subprocess.run(
        ["git", "add", "-N", "--", admitted_destination],
        cwd=repo,
        check=True,
    )
    assert _git_output(repo, "diff", "--cached", "--name-only", "--") == ""
    assert (
        _git_output(repo, "diff", "--name-only", "HEAD", "--")
        == admitted_destination
    )
    claim_inputs, claim_payloads = _real_claims(repo)
    routed = route_task(
        _route_facts(
            repo,
            claim_inputs,
            claim_payloads,
            dirty_scope=[admitted_destination],
        ),
        repo=repo,
        external_evidence_verifier=_strict_external_verifier(claim_payloads),
    )
    contract = task_contract_projection(routed["task_facts"])
    with pytest.raises(
        NativeEvidenceMismatch,
        match="protected allowed addition is not visible as untracked",
    ):
        acquire_task_admission(
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            task_contract=contract,
            external_evidence_verifier=_strict_external_verifier(
                contract["claim_payloads"]
            ),
        )


def test_lw2_lease_recaptures_generation_inside_lease_store_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _linked_main_evidence_repo(source, tmp_path)
    admission = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=deepcopy(contract),
        external_evidence_verifier=_strict_external_verifier(
            contract["claim_payloads"]
        ),
    )
    subprocess.run(
        ["git", "switch", "-q", "-c", "agent/lw2-lease-race"],
        cwd=repo,
        check=True,
    )
    original_transact = FileWriterLeaseStore.transact

    def mutate_before_lease_store(
        store: FileWriterLeaseStore,
        action: object,
    ) -> dict[str, object]:
        def mutate_inside_writer_lock(
            lease_state: dict[str, object],
            binding_state: dict[str, object],
        ) -> object:
            governed_source = repo / LW2_WRITABLE_PATH
            governed_source.write_text(
                governed_source.read_text(encoding="utf-8")
                + "\n# admission-to-lease lock race\n",
                encoding="utf-8",
            )
            return action(lease_state, binding_state)  # type: ignore[operator]

        return original_transact(store, mutate_inside_writer_lock)

    monkeypatch.setattr(
        FileWriterLeaseStore, "transact", mutate_before_lease_store
    )
    acquired = filesystem_writer_lease_action(
        action="acquire",
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        admission_id=admission["admission_id"],
    )

    assert acquired["status"] == "FAIL"
    assert acquired["reasons"] == ["TASK_ADMISSION_GENERATION_MISMATCH"]
    lease_store = FileWriterLeaseStore(inspect_worktree(repo).common_dir)
    assert lease_store.read()["leases"] == {}
    assert lease_store.state_path.exists() is False


def test_lw2_task_id_and_profile_are_cross_bound_before_admission_state(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, lw2_contract = real_lw2_contract
    repo = _clone_evidence_repo(source, tmp_path)
    with pytest.raises(ValueError, match="exact canonical binding"):
        acquire_task_admission(
            repo=repo,
            task_id="NOT-LW2",
            owner="E1",
            task_contract=lw2_contract,
            external_evidence_verifier=_strict_external_verifier(
                lw2_contract["claim_payloads"]
            ),
        )

    ordinary = route_task({
        "task_shape": "implementation",
        "surfaces": ["python"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "objective": "ordinary implementation contract",
        "scope": [
            "helper_scripts/maintenance_scripts/"
            "agent_governance_lw2_readmission.py",
        ],
        "dirty_scope": [
            "helper_scripts/maintenance_scripts/"
            "agent_governance_lw2_readmission.py",
        ],
    })
    with pytest.raises(ValueError, match="exact canonical binding"):
        acquire_task_admission(
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            task_contract=task_contract_projection(ordinary["task_facts"]),
        )
    _assert_no_admission_or_lease(repo)


def test_lw2_admission_binds_declared_writer_to_owner_and_rejects_self_review(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _clone_evidence_repo(source, tmp_path)
    for owner in ("OTHER", "E2"):
        with pytest.raises(ValueError, match="differs from admission owner"):
            acquire_task_admission(
                repo=repo,
                task_id="S2E-LW2",
                owner=owner,
                task_contract=deepcopy(contract),
                external_evidence_verifier=_strict_external_verifier(
                    contract["claim_payloads"]
                ),
            )

    self_review = deepcopy(contract)
    self_review["claim_inputs"], self_review["claim_payloads"] = (
        _invalid_claims(
            "review_self_identity",
            claim_inputs=self_review["claim_inputs"],
            claim_payloads=self_review["claim_payloads"],
        )
    )
    with pytest.raises(ValueError, match="not self-review"):
        acquire_task_admission(
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            task_contract=self_review,
            external_evidence_verifier=_strict_external_verifier(
                contract["claim_payloads"]
            ),
        )
    _assert_no_admission_or_lease(repo)
