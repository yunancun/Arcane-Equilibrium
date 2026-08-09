from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
HELPERS = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
for candidate in (ML_ROOT, HELPERS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


from aiml_gate_receipt_s2e_source_readiness import (
    S2EWaveOwnedSource,
    S2EWaveSourceDiagnosticCode,
    S2EWaveSourceReadinessStatus,
    s2e_wave_source_readiness_v1,
)
import aiml_gate_receipt_s2e_launch as launch
import aiml_gate_receipt_s2e_review as review
import agent_governance_s2e_lw1_action_packet as action


def _git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "S2E Source Readiness Test")
    _git(repo, "config", "user.email", "s2e-source-readiness@example.invalid")
    (repo / "owned").mkdir()
    (repo / "owned" / "runner.py").write_text("RUNNER = True\n", encoding="ascii")
    (repo / "owned" / "contract.json").write_text("{}\n", encoding="ascii")
    (repo / "unrelated.txt").write_text("unrelated\n", encoding="ascii")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "source checkpoint")
    return repo


def _manifest(head: str) -> tuple[S2EWaveOwnedSource, ...]:
    return (
        S2EWaveOwnedSource("owned/runner.py", head),
        S2EWaveOwnedSource("owned/contract.json", head),
    )


def _inventory() -> dict:
    return {
        "schema_version": action.INVENTORY_SCHEMA_VERSION,
        "host": "trade-core",
        "observed_at": "2026-08-10T00:00:00Z",
        "evidence_class": "UNAUTHENTICATED_READ_ONLY_OBSERVATION",
        "linux_source_head": "8" * 40,
        "linux_worktree_clean": True,
        "fixed_path_statuses": {
            path: "ABSENT" for path in action.EXPECTED_PATHS
        },
        "service_statuses": {
            item_id: "NOT_CONFIGURED"
            for item_id in action.EXPECTED_SERVICE_IDS
        },
        "runtime_units": [
            {
                "unit": "arcane-equilibrium-aiml-engine-scanner.service",
                "load_state": "not-found",
                "active_state": "inactive",
                "sub_state": "dead",
            },
            {
                "unit": "openclaw-learning.service",
                "load_state": "not-found",
                "active_state": "inactive",
                "sub_state": "dead",
            },
        ],
        "canonical_roots": [
            {"path": "/opt/arcane-equilibrium/aiml", "status": "ABSENT"},
            {"path": "/var/lib/arcane-equilibrium/aiml", "status": "ABSENT"},
        ],
    }


def test_same_generation_regular_blobs_are_source_ready(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=_manifest(head),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_READY
    assert readiness.wave == "S2E-LW1"
    assert readiness.generation == head
    assert readiness.owned_paths == ("owned/contract.json", "owned/runner.py")
    assert readiness.diagnostics == ()
    assert readiness.external_attested is False
    with pytest.raises((FrozenInstanceError, AttributeError)):
        readiness.external_attested = True  # type: ignore[misc]


@pytest.mark.parametrize("deleted", ("owned/runner.py", "owned/contract.json"))
def test_deleting_each_owned_path_is_source_incomplete(
    tmp_path: Path, deleted: str
) -> None:
    repo = _repo(tmp_path)
    _git(repo, "rm", "-q", deleted)
    _git(repo, "commit", "-qm", f"delete {deleted}")
    head = _git(repo, "rev-parse", "HEAD")

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=_manifest(head),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
    assert any(
        item.code is S2EWaveSourceDiagnosticCode.MISSING_PATH
        and item.path == deleted
        for item in readiness.diagnostics
    )


def test_unrelated_deletion_does_not_change_source_readiness(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "rm", "-q", "unrelated.txt")
    _git(repo, "commit", "-qm", "delete unrelated source")
    head = _git(repo, "rev-parse", "HEAD")

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=_manifest(head),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_READY
    assert readiness.diagnostics == ()


def test_readiness_uses_the_pinned_commit_not_the_current_worktree(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    pinned = _git(repo, "rev-parse", "HEAD")
    _git(repo, "rm", "-q", "owned/runner.py")
    _git(repo, "commit", "-qm", "delete owned path after pinned generation")

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=_manifest(pinned),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_READY
    assert readiness.generation == pinned


def test_executable_regular_blob_is_source_ready(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    os.chmod(repo / "owned" / "runner.py", 0o755)
    _git(repo, "add", "owned/runner.py")
    _git(repo, "commit", "-qm", "make runner executable")
    head = _git(repo, "rev-parse", "HEAD")

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=(S2EWaveOwnedSource("owned/runner.py", head),),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_READY


def test_mixed_manifest_generations_are_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = _git(repo, "rev-parse", "HEAD")
    (repo / "unrelated.txt").write_text("second\n", encoding="ascii")
    _git(repo, "add", "unrelated.txt")
    _git(repo, "commit", "-qm", "second generation")
    second = _git(repo, "rev-parse", "HEAD")

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=(
            S2EWaveOwnedSource("owned/runner.py", first),
            S2EWaveOwnedSource("owned/contract.json", second),
        ),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
    assert readiness.generation is None
    assert [item.code for item in readiness.diagnostics] == [
        S2EWaveSourceDiagnosticCode.MIXED_GENERATION
    ]


@pytest.mark.parametrize(
    "generation",
    (
        "HEAD",
        "HEAD^",
        "a" * 12,
        "A" * 40,
        "a" * 39,
        "a" * 41,
    ),
)
def test_refs_abbreviations_and_revision_expressions_are_rejected(
    tmp_path: Path, generation: str
) -> None:
    repo = _repo(tmp_path)

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=(
            S2EWaveOwnedSource("owned/runner.py", generation),
        ),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
    assert any(
        item.code is S2EWaveSourceDiagnosticCode.INVALID_GENERATION
        for item in readiness.diagnostics
    )


def test_repo_root_must_be_the_exact_worktree_top_level(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo / "owned",
        wave="S2E-LW1",
        owned_source_manifest=_manifest(head),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
    assert [item.code for item in readiness.diagnostics] == [
        S2EWaveSourceDiagnosticCode.REPO_ROOT_NOT_TOP_LEVEL
    ]


@pytest.mark.parametrize(
    "path",
    (
        "",
        "/owned/runner.py",
        ".",
        "./owned/runner.py",
        "owned/../owned/runner.py",
        "owned\\runner.py",
        "owned//runner.py",
        "owned/runner.py/",
        "C:/owned/runner.py",
        "owned/e\u0301.py",
    ),
)
def test_noncanonical_or_unsafe_paths_are_rejected(
    tmp_path: Path, path: str
) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=(S2EWaveOwnedSource(path, head),),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
    assert any(
        item.code is S2EWaveSourceDiagnosticCode.INVALID_PATH
        for item in readiness.diagnostics
    )


def test_duplicate_owned_paths_are_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=(
            S2EWaveOwnedSource("owned/runner.py", head),
            S2EWaveOwnedSource("owned/runner.py", head),
        ),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
    assert any(
        item.code is S2EWaveSourceDiagnosticCode.DUPLICATE_PATH
        for item in readiness.diagnostics
    )


def test_unknown_exact_commit_is_typed_source_incomplete(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=(
            S2EWaveOwnedSource("owned/runner.py", "f" * 40),
        ),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
    assert [item.code for item in readiness.diagnostics] == [
        S2EWaveSourceDiagnosticCode.INVALID_COMMIT
    ]


def test_exact_tag_object_id_is_not_accepted_as_a_commit_generation(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _git(repo, "tag", "-a", "checkpoint", "-m", "annotated checkpoint")
    tag_object = _git(repo, "rev-parse", "checkpoint^{tag}")

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=(
            S2EWaveOwnedSource("owned/runner.py", tag_object),
        ),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
    assert [item.code for item in readiness.diagnostics] == [
        S2EWaveSourceDiagnosticCode.INVALID_COMMIT
    ]


def test_non_repository_is_typed_source_incomplete(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()

    readiness = s2e_wave_source_readiness_v1(
        repo_root=not_a_repo,
        wave="S2E-LW1",
        owned_source_manifest=(
            S2EWaveOwnedSource("owned/runner.py", "f" * 40),
        ),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
    assert [item.code for item in readiness.diagnostics] == [
        S2EWaveSourceDiagnosticCode.INVALID_REPO_ROOT
    ]


@pytest.mark.parametrize("kind", ("symlink", "directory", "gitlink"))
def test_symlinks_directories_and_gitlinks_are_not_regular_owned_blobs(
    tmp_path: Path, kind: str
) -> None:
    repo = _repo(tmp_path)
    if kind == "symlink":
        os.symlink("runner.py", repo / "owned" / "candidate")
        _git(repo, "add", "owned/candidate")
    elif kind == "directory":
        (repo / "owned" / "candidate").mkdir()
        (repo / "owned" / "candidate" / "nested.py").write_text(
            "NESTED = True\n", encoding="ascii"
        )
        _git(repo, "add", "owned/candidate/nested.py")
    else:
        head = _git(repo, "rev-parse", "HEAD")
        _git(
            repo,
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{head},owned/candidate",
        )
    _git(repo, "commit", "-qm", f"add {kind}")
    head = _git(repo, "rev-parse", "HEAD")

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=(S2EWaveOwnedSource("owned/candidate", head),),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
    assert any(
        item.code is S2EWaveSourceDiagnosticCode.NON_REGULAR_BLOB
        for item in readiness.diagnostics
    )


def test_unreadable_owned_blob_is_typed_source_incomplete(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    blob = _git(repo, "rev-parse", f"{head}:owned/runner.py")
    (repo / ".git" / "objects" / blob[:2] / blob[2:]).unlink()

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=(S2EWaveOwnedSource("owned/runner.py", head),),
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
    assert [item.code for item in readiness.diagnostics] == [
        S2EWaveSourceDiagnosticCode.UNREADABLE_BLOB
    ]


def test_u1_source_ready_cannot_change_launch_transition_errors(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    invalid_request = {}
    transition_arguments = {
        "predecessor_receipt": {},
        "predecessor_authority": {},
        "repo_root": repo,
        "now": "2026-08-10T00:00:00Z",
        "consumed_predecessor_digests": frozenset(),
        "durability_anchor_attestation": {},
        "acceptance_review_bundle": {},
    }
    before = launch.validate_s2e_launch_transition(
        invalid_request, **transition_arguments
    )

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=_manifest(head),
    )
    after = launch.validate_s2e_launch_transition(
        invalid_request, **transition_arguments
    )

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_READY
    assert before
    assert after == before


def test_u2_readiness_cannot_be_a_receipt_candidate_or_issue_a_receipt(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=_manifest(head),
    )
    serialized = {
        "schema_version": "s2e_wave_source_readiness_v1",
        "status": readiness.status.value,
        "wave": readiness.wave,
        "generation": readiness.generation,
        "owned_paths": list(readiness.owned_paths),
        "diagnostics": [],
        "external_attested": readiness.external_attested,
    }

    assert launch.validate_s2e_launch_genesis_receipt(
        readiness, repo_root=repo
    )
    assert launch.validate_s2e_launch_wave_receipt(readiness, repo_root=repo)
    assert launch.validate_s2e_launch_genesis_receipt(serialized, repo_root=repo)
    assert launch.validate_s2e_launch_wave_receipt(serialized, repo_root=repo)
    for candidate in (readiness, serialized):
        issuance = launch.issue_s2e_launch_receipt(
            candidate,
            acceptance_review_bundle={},
            repo_root=repo,
        )
        assert issuance["status"] != "ISSUED"
        assert issuance["issued_receipt"] is None
        assert "launch receipt candidate schema is unsupported" in issuance["errors"]


def test_u3_source_readiness_cannot_project_package_source_landed(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    todo = repo / "TODO.md"
    todo.write_text(
        "| ID | Lane | Dependency | Work | Exit |\n"
        "|---|---|---|---|---|\n"
        "| `S2E.2b-2` | **ACTIVE / P0** | ready | LW1 | waiting |\n",
        encoding="utf-8",
    )
    _git(repo, "add", "TODO.md")
    _git(repo, "commit", "-qm", "add active package projection")
    head = _git(repo, "rev-parse", "HEAD")
    candidate = {
        "schema_version": "s2e_launch_wave_receipt_v1",
        "source_head": head,
        "source_tree": _git(repo, "rev-parse", f"{head}^{{tree}}"),
        "wave_exit_id": "not-authority",
    }
    manifest = [{
        "path": "TODO.md",
        "git_blob": _git(repo, "rev-parse", f"{head}:TODO.md"),
    }]
    before = review._exit_boundary_evidence(candidate, manifest, repo_root=repo)

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=(S2EWaveOwnedSource("TODO.md", head),),
    )
    after = review._exit_boundary_evidence(candidate, manifest, repo_root=repo)

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_READY
    assert after == before
    assert "**ACTIVE / P0**" in todo.read_text(encoding="utf-8")
    assert "SOURCE_LANDED" not in todo.read_text(encoding="utf-8")


def test_u4_source_readiness_cannot_touch_closure_or_authority_boundaries(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    before = action.build_s2e_lw1_operator_action_packet(
        repo_root=repo,
        inventory=_inventory(),
    )

    readiness = s2e_wave_source_readiness_v1(
        repo_root=repo,
        wave="S2E-LW1",
        owned_source_manifest=_manifest(head),
    )
    after = action.build_s2e_lw1_operator_action_packet(
        repo_root=repo,
        inventory=_inventory(),
    )

    schema = json.loads(action.SCHEMA_PATH.read_text(encoding="utf-8"))
    closure_properties = schema["$defs"]["closure_projection"]["properties"]
    closure_false_fields = {
        field
        for field, contract in closure_properties.items()
        if contract.get("const") is False
    }
    authority_properties = schema["$defs"]["authority_boundaries"]["properties"]
    authority_false_fields = {
        field
        for field, contract in authority_properties.items()
        if contract.get("const") is False
    }

    assert readiness.status is S2EWaveSourceReadinessStatus.SOURCE_READY
    assert after["closure_projection"] == before["closure_projection"]
    assert closure_false_fields == {
        "w0_genesis_receipt_issued",
        "lw1_wave_receipt_issued",
        "lw1_transition_gate_advance",
        "lw2_unlocked",
        "s2e_2b_2_closed",
        "s2_closed",
    }
    assert all(
        before["closure_projection"][field] is False
        and after["closure_projection"][field] is False
        for field in closure_false_fields
    )
    assert authority_false_fields == {
        "production_runtime_effect_performed_by_task",
        "production_deploy_restart_pg_broker_order_authorized",
    }
    assert all(
        before["authority_boundaries"][field] is False
        and after["authority_boundaries"][field] is False
        for field in authority_false_fields
    )
    assert "production_runtime_effect_performed_by_task" not in (
        after["closure_projection"]
    )
    assert after["authority_boundaries"] == before["authority_boundaries"]
