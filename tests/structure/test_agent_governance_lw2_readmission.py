"""Executable current-head admission binding for the future S2E LW2 task."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_lw2_readmission import (  # noqa: E402
    LW2_ADMISSION_PROFILE,
    validate_lw2_readmission_eligibility,
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
    inspect_worktree,
)


HEAD = "1" * 40
TREE = "2" * 40


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
    identity = {
        "schema_version": "lw2_combined_main_identity_v1",
        "head": head,
        "tree": tree,
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


def _rebind(payloads: dict[str, object]) -> dict[str, str]:
    capture_digest = _digest(
        payloads["lw2_combined_main_unreachability_capture"]
    )
    payloads["lw2_independent_review"]["reviewed_capture_digest"] = (
        capture_digest
    )
    return {key: _digest(value) for key, value in payloads.items()}


def _invalid_claims(
    case: str, *, head: str, tree: str,
) -> tuple[dict[str, str], dict[str, object]]:
    claim_inputs, claim_payloads = _claims(head=head, tree=tree)
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
        claim_inputs = _rebind(claim_payloads)
    elif case == "stale_head":
        for payload in claim_payloads.values():
            payload["head"] = "3" * 40
        claim_inputs = _rebind(claim_payloads)
    elif case == "stale_tree":
        for payload in claim_payloads.values():
            payload["tree"] = "4" * 40
        claim_inputs = _rebind(claim_payloads)
    elif case == "stale_capture_head":
        claim_payloads["lw2_combined_main_unreachability_capture"]["head"] = "3" * 40
        claim_inputs = _rebind(claim_payloads)
    elif case == "capture_non_pass":
        claim_payloads["lw2_combined_main_unreachability_capture"]["status"] = "FAIL"
        claim_inputs = _rebind(claim_payloads)
    elif case == "capture_non_governed":
        claim_payloads["lw2_combined_main_unreachability_capture"]["governed"] = False
        claim_inputs = _rebind(claim_payloads)
    elif case == "review_non_pass":
        claim_payloads["lw2_independent_review"]["status"] = "FAIL"
        claim_inputs = {
            key: _digest(value) for key, value in claim_payloads.items()
        }
    elif case == "review_self_identity":
        claim_payloads["lw2_independent_review"]["reviewer_identity"] = (
            claim_payloads["lw2_independent_review"]["writer_identity"]
        )
        claim_inputs = {
            key: _digest(value) for key, value in claim_payloads.items()
        }
    elif case == "wrong_reviewed_capture_digest":
        claim_payloads["lw2_independent_review"]["reviewed_capture_digest"] = (
            "sha256:" + "f" * 64
        )
        claim_inputs = {
            key: _digest(value) for key, value in claim_payloads.items()
        }
    else:
        raise AssertionError(case)
    return claim_inputs, claim_payloads


def test_three_fresh_same_head_lw2_claims_are_eligible_only() -> None:
    claim_inputs, claim_payloads = _claims()

    assert validate_lw2_readmission_eligibility(
        admission_profile=LW2_ADMISSION_PROFILE,
        claim_inputs=claim_inputs,
        claim_payloads=claim_payloads,
        current_head=HEAD,
        current_tree=TREE,
    ) is True


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
        "capture_non_pass",
        "capture_non_governed",
        "review_non_pass",
        "review_self_identity",
        "wrong_reviewed_capture_digest",
    ],
)
def test_lw2_pure_validator_fails_closed_for_every_binding_break(case: str) -> None:
    claim_inputs, claim_payloads = _invalid_claims(case, head=HEAD, tree=TREE)
    with pytest.raises(ValueError):
        validate_lw2_readmission_eligibility(
            admission_profile=LW2_ADMISSION_PROFILE,
            claim_inputs=claim_inputs,
            claim_payloads=claim_payloads,
            current_head=HEAD,
            current_tree=TREE,
        )


def _init_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owned.py").write_text("VALUE = 1\n", encoding="utf-8")
    for args in (
        ("init",),
        ("config", "user.email", "lw2-test@example.invalid"),
        ("config", "user.name", "LW2 Test"),
        ("add", "."),
        ("commit", "-m", "baseline"),
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    return repo, head, tree


def _route_facts(head: str, tree: str) -> dict[str, object]:
    claim_inputs, claim_payloads = _claims(head=head, tree=tree)
    return {
        "task_shape": "implementation",
        "surfaces": ["python", "governance"],
        "risk": "high",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "objective": "implement the separately admitted future S2E LW2 source unit",
        "scope": ["owned.py"],
        "dirty_scope": ["owned.py"],
        "acceptance_criteria": ["fresh LW2 evidence is bound before work"],
        "hard_stops": ["no runtime or trading effect"],
        "direct_interfaces": ["S2E-LW2"],
        "previous_failure": "fresh combined-main evidence was not executable",
        "admission_profile": LW2_ADMISSION_PROFILE,
        "claim_inputs": claim_inputs,
        "claim_payloads": claim_payloads,
    }


def test_lw2_route_validates_current_claims_before_constructing_the_dag(
    tmp_path: Path,
) -> None:
    repo, head, tree = _init_repo(tmp_path)
    facts = _route_facts(head, tree)

    routed = route_task(facts, repo=repo)

    assert routed["task_facts"]["admission_profile"] == LW2_ADMISSION_PROFILE
    assert task_contract_projection(routed["task_facts"])["claim_payloads"] == (
        facts["claim_payloads"]
    )
    missing = dict(facts)
    missing["claim_inputs"] = dict(facts["claim_inputs"])
    missing["claim_payloads"] = dict(facts["claim_payloads"])
    missing["claim_inputs"].pop("lw2_independent_review")
    missing["claim_payloads"].pop("lw2_independent_review")
    with pytest.raises(ValueError, match="exactly three"):
        route_task(missing, repo=repo)


def test_every_invalid_lw2_route_stops_before_returning_a_dag(
    tmp_path: Path,
) -> None:
    repo, head, tree = _init_repo(tmp_path)
    cases = [
        "missing_lw2_combined_main_identity",
        "missing_lw2_combined_main_unreachability_capture",
        "missing_lw2_independent_review",
        "extra_claim",
        "payload_replacement",
        "malformed_raw_head",
        "stale_head",
        "stale_tree",
        "stale_capture_head",
        "capture_non_pass",
        "capture_non_governed",
        "review_non_pass",
        "review_self_identity",
        "wrong_reviewed_capture_digest",
    ]
    for case in cases:
        claim_inputs, claim_payloads = _invalid_claims(case, head=head, tree=tree)
        facts = _route_facts(head, tree)
        facts["claim_inputs"] = claim_inputs
        facts["claim_payloads"] = claim_payloads
        dag = None
        with pytest.raises(ValueError):
            dag = route_task(facts, repo=repo)
        assert dag is None, case


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
    assert routed["task_facts"]["claim_payloads"] == {}
    contract = task_contract_projection(routed["task_facts"])
    assert contract["admission_profile"] is None
    assert contract["claim_payloads"] == {}

    plan = compile_context("E1", routed["task_facts"], root=ROOT)
    artifact = materialize_context_artifact(plan)
    validation = validate_context_artifact(
        artifact,
        expected_task_facts=routed["task_facts"],
    )
    assert validation["errors"] == []


def test_lw2_task_admission_revalidates_current_head_before_store_mutation(
    tmp_path: Path,
) -> None:
    repo, head, tree = _init_repo(tmp_path)
    routed = route_task(_route_facts(head, tree), repo=repo)
    contract = task_contract_projection(routed["task_facts"])
    (repo / "owned.py").write_text("VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "owned.py"], cwd=repo, check=True)
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
        )

    identity = inspect_worktree(repo)
    store = FileTaskAdmissionStore(identity.common_dir)
    assert store.read()["admissions"] == {}
    assert store.state_path.exists() is False
    lease_store = FileWriterLeaseStore(identity.common_dir)
    assert lease_store.read()["leases"] == {}
    assert lease_store.state_path.exists() is False


def test_lw2_route_cli_returns_typed_failure_without_a_dag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo, head, tree = _init_repo(tmp_path)
    facts = _route_facts(head, tree)
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
    assert "exactly three" in result["error"]
    assert "nodes" not in result
    assert "dag_digest" not in result


def test_eligible_temp_repo_admission_never_auto_creates_a_writer_lease(
    tmp_path: Path,
) -> None:
    repo, head, tree = _init_repo(tmp_path)
    routed = route_task(_route_facts(head, tree), repo=repo)
    result = acquire_task_admission(
        repo=repo,
        task_id="S2E-LW2",
        owner="E1",
        task_contract=task_contract_projection(routed["task_facts"]),
    )

    assert result["status"] == "PASS"
    common_dir = inspect_worktree(repo).common_dir
    assert FileTaskAdmissionStore(common_dir).read()["admissions"]
    lease_store = FileWriterLeaseStore(common_dir)
    assert lease_store.read()["leases"] == {}
    assert lease_store.state_path.exists() is False


def test_lw2_task_id_and_profile_are_cross_bound_before_admission_state(
    tmp_path: Path,
) -> None:
    repo, head, tree = _init_repo(tmp_path)
    lw2_contract = task_contract_projection(
        route_task(_route_facts(head, tree), repo=repo)["task_facts"]
    )
    with pytest.raises(ValueError, match="canonical task_id S2E-LW2"):
        acquire_task_admission(
            repo=repo,
            task_id="NOT-LW2",
            owner="E1",
            task_contract=lw2_contract,
        )

    ordinary = route_task({
        "task_shape": "implementation",
        "surfaces": ["python"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "objective": "ordinary implementation contract",
        "scope": ["owned.py"],
        "dirty_scope": ["owned.py"],
    })
    with pytest.raises(ValueError, match="requires the exact LW2 admission_profile"):
        acquire_task_admission(
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            task_contract=task_contract_projection(ordinary["task_facts"]),
        )
    store = FileTaskAdmissionStore(inspect_worktree(repo).common_dir)
    assert store.read()["admissions"] == {}
    assert store.state_path.exists() is False


def test_lw2_admission_binds_declared_writer_to_owner_and_rejects_self_review(
    tmp_path: Path,
) -> None:
    repo, head, tree = _init_repo(tmp_path)
    contract = task_contract_projection(
        route_task(_route_facts(head, tree), repo=repo)["task_facts"]
    )
    with pytest.raises(ValueError, match="differs from admission owner"):
        acquire_task_admission(
            repo=repo,
            task_id="S2E-LW2",
            owner="OTHER",
            task_contract=contract,
        )

    self_review = deepcopy(contract)
    review = self_review["claim_payloads"]["lw2_independent_review"]
    review["reviewer_identity"] = review["writer_identity"]
    self_review["claim_inputs"]["lw2_independent_review"] = _digest(review)
    with pytest.raises(ValueError, match="not self-review"):
        acquire_task_admission(
            repo=repo,
            task_id="S2E-LW2",
            owner="E1",
            task_contract=self_review,
        )
    store = FileTaskAdmissionStore(inspect_worktree(repo).common_dir)
    assert store.read()["admissions"] == {}
    assert store.state_path.exists() is False
