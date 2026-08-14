"""Executable current-head admission binding for the future S2E LW2 task."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_lw2_readmission import (  # noqa: E402
    LW2_ADMISSION_PROFILE,
    lw2_contract_selected,
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
)
from agent_governance import main as governance_main  # noqa: E402
from agent_governance_writer_lease import (  # noqa: E402
    FileWriterLeaseStore,
    filesystem_writer_lease_action,
    inspect_worktree,
)


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


def _trusted_external_verifier(request: dict[str, object]) -> bool:
    return (
        request.get("schema_version") in {
            "lw2_publication_verification_request_v1",
            "lw2_independent_review_verification_request_v1",
        }
        and request.get("repository_url") == LW2_REPOSITORY_URL
        and request.get("destination_ref") == LW2_DESTINATION_REF
        and isinstance(request.get("head"), str)
        and isinstance(request.get("tree"), str)
    )


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
    subprocess.run(
        ["git", "clone", "--quiet", str(ROOT), str(repo)],
        check=True,
        capture_output=True,
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
        external_evidence_verifier=_trusted_external_verifier,
    ) is True


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


def test_handwritten_summary_only_lw2_claims_are_ineligible(
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> None:
    repo, _, _ = real_lw2_evidence
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
            external_evidence_verifier=_trusted_external_verifier,
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
            external_evidence_verifier=_trusted_external_verifier,
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
            ["git", "remote", "set-url", "origin", "https://example.invalid/repo.git"],
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
            external_evidence_verifier=_trusted_external_verifier,
        )


def _route_facts(
    repo: Path,
    claim_inputs: dict[str, str],
    claim_payloads: dict[str, object],
) -> dict[str, object]:
    return {
        "task_shape": "implementation",
        "surfaces": ["python", "governance"],
        "risk": "high",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "objective": "implement the separately admitted future S2E LW2 source unit",
        "scope": [
            "helper_scripts/maintenance_scripts/"
            "agent_governance_lw2_readmission.py",
        ],
        "dirty_scope": [
            "helper_scripts/maintenance_scripts/"
            "agent_governance_lw2_readmission.py",
        ],
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
        external_evidence_verifier=_trusted_external_verifier,
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
            external_evidence_verifier=_trusted_external_verifier,
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


@pytest.fixture(scope="module")
def real_lw2_contract(
    real_lw2_evidence: tuple[Path, dict[str, str], dict[str, object]],
) -> tuple[Path, dict[str, object]]:
    repo, claim_inputs, claim_payloads = real_lw2_evidence
    routed = route_task(
        _route_facts(repo, claim_inputs, claim_payloads),
        repo=repo,
        external_evidence_verifier=_trusted_external_verifier,
    )
    return repo, task_contract_projection(routed["task_facts"])


def _clone_evidence_repo(source: Path, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    subprocess.run(
        ["git", "clone", "--quiet", str(source), str(repo)],
        check=True,
        capture_output=True,
    )
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
    return repo


def _assert_no_admission_or_lease(repo: Path) -> None:
    identity = inspect_worktree(repo)
    store = FileTaskAdmissionStore(identity.common_dir)
    assert store.read()["admissions"] == {}
    assert store.state_path.exists() is False
    assert store.lock_path.exists() is False
    lease_store = FileWriterLeaseStore(identity.common_dir)
    assert lease_store.read()["leases"] == {}
    assert lease_store.state_path.exists() is False


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
            external_evidence_verifier=_trusted_external_verifier,
        )

    _assert_no_admission_or_lease(repo)


def test_lw2_task_admission_replays_before_store_and_rejects_dirty_generation(
    tmp_path: Path,
    real_lw2_contract: tuple[Path, dict[str, object]],
) -> None:
    source, contract = real_lw2_contract
    repo = _clone_evidence_repo(source, tmp_path)
    governed_source = (
        repo / "helper_scripts" / "maintenance_scripts"
        / "agent_governance_lw2_readmission.py"
    )
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
            external_evidence_verifier=_trusted_external_verifier,
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
        governed_source = (
            repo / "helper_scripts" / "maintenance_scripts"
            / "agent_governance_lw2_readmission.py"
        )
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
            external_evidence_verifier=_trusted_external_verifier,
        )

    identity = inspect_worktree(repo)
    assert FileTaskAdmissionStore(identity.common_dir).read()["admissions"] == {}
    assert FileTaskAdmissionStore(identity.common_dir).state_path.exists() is False
    assert FileWriterLeaseStore(identity.common_dir).read()["leases"] == {}


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
        external_evidence_verifier=_trusted_external_verifier,
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
    lease_store = FileWriterLeaseStore(common_dir)
    assert lease_store.read()["leases"] == {}
    assert lease_store.state_path.exists() is False


def test_direct_lw2_lease_requires_exact_admission_token_and_generation(
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
        external_evidence_verifier=_trusted_external_verifier,
    )
    assert admission["status"] == "PASS"

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

    governed_source = (
        repo / "helper_scripts" / "maintenance_scripts"
        / "agent_governance_lw2_readmission.py"
    )
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
            external_evidence_verifier=_trusted_external_verifier,
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
            external_evidence_verifier=_trusted_external_verifier,
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
                external_evidence_verifier=_trusted_external_verifier,
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
            external_evidence_verifier=_trusted_external_verifier,
        )
    _assert_no_admission_or_lease(repo)
