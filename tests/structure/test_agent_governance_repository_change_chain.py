"""Ordered multi-writer repository generation chain tests."""

from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_capture import capture_repository  # noqa: E402
from agent_governance_repository_changes import (  # noqa: E402
    capture_repository_change,
    validate_repository_change_chain,
)
from agent_governance_trust import _mutation_errors  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_multiple_admitted_writers_form_one_current_generation_chain(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "chain@example.invalid")
    _git(repo, "config", "user.name", "Chain Test")
    (repo / "one.txt").write_text("before\n", encoding="utf-8")
    (repo / "two.txt").write_text("before\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")
    scope = ["one.txt", "two.txt"]
    writer_scopes = {
        "implementation": ["one.txt"],
        "docs_projection": ["two.txt"],
    }
    task_digest = "sha256:" + "a" * 64

    before = capture_repository(scope, root=repo)
    owned_before = capture_repository(writer_scopes["implementation"], root=repo)
    (repo / "one.txt").write_text("writer one\n", encoding="utf-8")
    first = capture_repository_change(
        before=before, task_contract_digest=task_digest,
        node_id="implementation", role_id="E1",
        scope=writer_scopes["implementation"], owned_before=owned_before, root=repo,
    )
    before_docs = capture_repository(scope, root=repo)
    owned_before_docs = capture_repository(writer_scopes["docs_projection"], root=repo)
    (repo / "two.txt").write_text("writer two\n", encoding="utf-8")
    second = capture_repository_change(
        before=before_docs, task_contract_digest=task_digest,
        node_id="docs_projection", role_id="TW",
        scope=writer_scopes["docs_projection"], owned_before=owned_before_docs,
        root=repo,
    )

    assert first["after_generation_digest"] == second["before_generation_digest"]

    assert validate_repository_change_chain(
        [first, second], expected_writer_scopes=writer_scopes, root=repo,
    ) == []
    packet = {
        "disposition": "CHANGED",
        "side_effects": {"repo_mutation": True},
        "role_fragments": [
            {
                "node_id": record["node_id"],
                "role": record["role_id"],
                "evidence_refs": [evidence_id],
            }
            for evidence_id, record in (("change:first", first), ("change:second", second))
        ],
    }
    assert _mutation_errors(
        packet,
        {"changes": {"change:first": first, "change:second": second}},
    ) == []

    reversed_errors = validate_repository_change_chain(
        [second, first], expected_writer_scopes=writer_scopes, root=repo,
    )
    assert any("writer order differs" in error for error in reversed_errors)

    broken_generation = deepcopy(second)
    broken_generation["before_generation_digest"] = "sha256:" + "c" * 64
    generation_errors = validate_repository_change_chain(
        [first, broken_generation], expected_writer_scopes=writer_scopes, root=repo,
    )
    assert any(
        "before generation does not equal the preceding writer after generation"
        in error for error in generation_errors
    )

    verification_errors = validate_repository_change_chain(
        [first, second],
        expected_writer_scopes={"implementation": ["one.txt"]}, root=repo,
    )
    assert any("writer coverage differs" in error for error in verification_errors)

    missing_writer_errors = validate_repository_change_chain(
        [first], expected_writer_scopes=writer_scopes, root=repo,
    )
    assert any("writer coverage differs" in error for error in missing_writer_errors)

    mixed_scope = capture_repository(scope, root=repo)
    (repo / "one.txt").write_text("mixed writer\n", encoding="utf-8")
    mixed_record = capture_repository_change(
        before=mixed_scope, task_contract_digest=task_digest,
        node_id="implementation", role_id="E1", scope=scope, root=repo,
    )
    mixed_errors = validate_repository_change_chain(
        [mixed_record], expected_writer_scopes=writer_scopes, root=repo,
    )
    assert any("writer coverage differs" in error for error in mixed_errors)
    assert any("expected node-owned scope" in error for error in mixed_errors)

    (repo / "two.txt").write_text("uncaptured drift\n", encoding="utf-8")
    stale_errors = validate_repository_change_chain(
        [first, second], expected_writer_scopes=writer_scopes, root=repo,
    )
    assert any("writer after" in error and "stale" in error for error in stale_errors)


def test_full_stack_builders_and_docs_each_need_their_own_current_record(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "full-stack"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "full-stack@example.invalid")
    _git(repo, "config", "user.name", "Full Stack Test")
    for path in ("api.py", "App.tsx", "console.md"):
        (repo / path).write_text("before\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")
    task_digest = "sha256:" + "b" * 64
    contracts = [
        ("implementation_backend", "E1", ["api.py"]),
        ("implementation_frontend", "E1a", ["App.tsx"]),
        ("docs_projection", "TW", ["console.md"]),
    ]
    generation_scope = sorted(
        path for _node_id, _role, scope in contracts for path in scope
    )
    records = []
    for node_id, role, scope in contracts:
        before = capture_repository(generation_scope, root=repo)
        owned_before = capture_repository(scope, root=repo)
        (repo / scope[0]).write_text(f"changed by {node_id}\n", encoding="utf-8")
        records.append(capture_repository_change(
            before=before, task_contract_digest=task_digest,
            node_id=node_id, role_id=role, scope=scope,
            owned_before=owned_before, root=repo,
        ))
    writer_scopes = {node_id: scope for node_id, _role, scope in contracts}
    assert validate_repository_change_chain(
        records, expected_writer_scopes=writer_scopes, root=repo,
    ) == []
    missing_frontend = validate_repository_change_chain(
        [records[0], records[2]], expected_writer_scopes=writer_scopes, root=repo,
    )
    assert any("writer coverage differs" in error for error in missing_frontend)
