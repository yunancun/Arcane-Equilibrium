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
    _record_digest,
    capture_repository_change,
    validate_repository_change_chain,
)
from agent_governance_trust import _mutation_errors  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


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


def test_committed_disjoint_writer_ranges_require_only_the_final_endpoint_current(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "committed-chain"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "committed@example.invalid")
    _git(repo, "config", "user.name", "Committed Chain")
    for path in ("one.txt", "two.txt"):
        (repo / path).write_text("before\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")
    baseline_head = _head(repo)
    task_digest = "sha256:" + "c" * 64
    writer_scopes = {
        "implementation": ["one.txt"],
        "docs_projection": ["two.txt"],
    }
    generation_scope = ["one.txt", "two.txt"]

    before = capture_repository(generation_scope, root=repo)
    owned_before = capture_repository(["one.txt"], root=repo)
    (repo / "one.txt").write_text("writer one\n", encoding="utf-8")
    _git(repo, "add", "one.txt")
    _git(repo, "commit", "-qm", "writer one")
    first = capture_repository_change(
        before=before, task_contract_digest=task_digest,
        node_id="implementation", role_id="E1", scope=["one.txt"],
        owned_before=owned_before, root=repo,
    )

    before = capture_repository(generation_scope, root=repo)
    owned_before = capture_repository(["two.txt"], root=repo)
    (repo / "two.txt").write_text("writer two\n", encoding="utf-8")
    _git(repo, "add", "two.txt")
    _git(repo, "commit", "-qm", "writer two")
    second = capture_repository_change(
        before=before, task_contract_digest=task_digest,
        node_id="docs_projection", role_id="TW", scope=["two.txt"],
        owned_before=owned_before, root=repo,
    )

    assert validate_repository_change_chain(
        [first, second], expected_writer_scopes=writer_scopes,
        expected_writer_roles={"implementation": "E1", "docs_projection": "TW"},
        expected_source_head=baseline_head, root=repo,
    ) == []

    wrong_role = deepcopy(second)
    wrong_role["role_id"] = "E1"
    wrong_role["record_digest"] = _record_digest(wrong_role)
    role_errors = validate_repository_change_chain(
        [first, wrong_role], expected_writer_scopes=writer_scopes,
        expected_writer_roles={"implementation": "E1", "docs_projection": "TW"},
        expected_source_head=baseline_head, root=repo,
    )
    assert any("expected writer role" in error for error in role_errors)

    endpoint_mismatch = deepcopy(first)
    endpoint_mismatch["owned_after"]["source_head"] = baseline_head
    endpoint_mismatch["owned_after"]["record_digest"] = (
        endpoint_mismatch["owned_before"]["record_digest"]
    )
    endpoint_mismatch["owned_after_generation_digest"] = (
        endpoint_mismatch["owned_before_generation_digest"]
    )
    endpoint_mismatch["record_digest"] = _record_digest(endpoint_mismatch)
    endpoint_errors = validate_repository_change_chain(
        [endpoint_mismatch, second], expected_writer_scopes=writer_scopes,
        expected_source_head=baseline_head, root=repo,
    )
    assert any("task and owned endpoint heads differ" in error for error in endpoint_errors)

    (repo / "two.txt").write_text("final drift\n", encoding="utf-8")
    drift_errors = validate_repository_change_chain(
        [first, second], expected_writer_scopes=writer_scopes,
        expected_source_head=baseline_head, root=repo,
    )
    assert any("final generation" in error and "stale" in error for error in drift_errors)


def test_committed_ranges_reject_later_touch_revert_rename_merge_and_empty_commit(
    tmp_path: Path,
) -> None:
    task_digest = "sha256:" + "d" * 64

    touch_repo = tmp_path / "touch-revert"
    touch_repo.mkdir()
    _git(touch_repo, "init", "-q")
    _git(touch_repo, "config", "user.email", "touch@example.invalid")
    _git(touch_repo, "config", "user.name", "Touch Test")
    for path in ("one.txt", "two.txt"):
        (touch_repo / path).write_text("before\n", encoding="utf-8")
    _git(touch_repo, "add", ".")
    _git(touch_repo, "commit", "-qm", "fixture")
    baseline_head = _head(touch_repo)
    generation_scope = ["one.txt", "two.txt"]
    before = capture_repository(generation_scope, root=touch_repo)
    owned_before = capture_repository(["one.txt"], root=touch_repo)
    (touch_repo / "one.txt").write_text("writer one\n", encoding="utf-8")
    _git(touch_repo, "add", "one.txt")
    _git(touch_repo, "commit", "-qm", "writer one")
    first = capture_repository_change(
        before=before, task_contract_digest=task_digest,
        node_id="implementation", role_id="E1", scope=["one.txt"],
        owned_before=owned_before, root=touch_repo,
    )
    before = capture_repository(generation_scope, root=touch_repo)
    owned_before = capture_repository(["two.txt"], root=touch_repo)
    (touch_repo / "one.txt").write_text("illegal later touch\n", encoding="utf-8")
    _git(touch_repo, "add", "one.txt")
    _git(touch_repo, "commit", "-qm", "touch earlier scope")
    (touch_repo / "one.txt").write_text("writer one\n", encoding="utf-8")
    (touch_repo / "two.txt").write_text("writer two\n", encoding="utf-8")
    _git(touch_repo, "add", "one.txt", "two.txt")
    _git(touch_repo, "commit", "-qm", "revert touch and write owned scope")
    second = capture_repository_change(
        before=before, task_contract_digest=task_digest,
        node_id="docs_projection", role_id="TW", scope=["two.txt"],
        owned_before=owned_before, root=touch_repo,
    )
    touch_errors = validate_repository_change_chain(
        [first, second],
        expected_writer_scopes={
            "implementation": ["one.txt"], "docs_projection": ["two.txt"],
        },
        expected_source_head=baseline_head, root=touch_repo,
    )
    assert any("commit paths exceed writer scope" in error for error in touch_errors)

    rename_repo = tmp_path / "rename"
    rename_repo.mkdir()
    _git(rename_repo, "init", "-q")
    _git(rename_repo, "config", "user.email", "rename@example.invalid")
    _git(rename_repo, "config", "user.name", "Rename Test")
    (rename_repo / "owned.txt").write_text("before\n", encoding="utf-8")
    _git(rename_repo, "add", "owned.txt")
    _git(rename_repo, "commit", "-qm", "fixture")
    rename_head = _head(rename_repo)
    before = capture_repository(["owned.txt"], root=rename_repo)
    _git(rename_repo, "mv", "owned.txt", "outside.txt")
    _git(rename_repo, "commit", "-qm", "rename outside scope")
    renamed = capture_repository_change(
        before=before, task_contract_digest=task_digest,
        node_id="implementation", role_id="E1", scope=["owned.txt"],
        owned_before=before, root=rename_repo,
    )
    rename_errors = validate_repository_change_chain(
        [renamed], expected_writer_scopes={"implementation": ["owned.txt"]},
        expected_source_head=rename_head, root=rename_repo,
    )
    assert any("commit paths exceed writer scope" in error for error in rename_errors)

    empty_repo = tmp_path / "empty"
    empty_repo.mkdir()
    _git(empty_repo, "init", "-q")
    _git(empty_repo, "config", "user.email", "empty@example.invalid")
    _git(empty_repo, "config", "user.name", "Empty Test")
    (empty_repo / "owned.txt").write_text("before\n", encoding="utf-8")
    _git(empty_repo, "add", "owned.txt")
    _git(empty_repo, "commit", "-qm", "fixture")
    empty_head = _head(empty_repo)
    before = capture_repository(["owned.txt"], root=empty_repo)
    _git(empty_repo, "commit", "--allow-empty", "-qm", "empty writer")
    empty = capture_repository_change(
        before=before, task_contract_digest=task_digest,
        node_id="implementation", role_id="E1", scope=["owned.txt"],
        owned_before=before, root=empty_repo,
    )
    empty_errors = validate_repository_change_chain(
        [empty], expected_writer_scopes={"implementation": ["owned.txt"]},
        expected_source_head=empty_head, root=empty_repo,
    )
    assert any("empty commit" in error for error in empty_errors)

    merge_repo = tmp_path / "merge"
    merge_repo.mkdir()
    _git(merge_repo, "init", "-q")
    _git(merge_repo, "config", "user.email", "merge@example.invalid")
    _git(merge_repo, "config", "user.name", "Merge Test")
    for path in ("one.txt", "two.txt"):
        (merge_repo / path).write_text("before\n", encoding="utf-8")
    _git(merge_repo, "add", ".")
    _git(merge_repo, "commit", "-qm", "fixture")
    merge_head = _head(merge_repo)
    before = capture_repository(["one.txt", "two.txt"], root=merge_repo)
    _git(merge_repo, "switch", "-qc", "side")
    (merge_repo / "one.txt").write_text("side\n", encoding="utf-8")
    _git(merge_repo, "add", "one.txt")
    _git(merge_repo, "commit", "-qm", "side")
    _git(merge_repo, "switch", "-q", "master")
    (merge_repo / "two.txt").write_text("main\n", encoding="utf-8")
    _git(merge_repo, "add", "two.txt")
    _git(merge_repo, "commit", "-qm", "main")
    _git(merge_repo, "merge", "--no-ff", "-qm", "merge", "side")
    merged = capture_repository_change(
        before=before, task_contract_digest=task_digest,
        node_id="implementation", role_id="E1",
        scope=["one.txt", "two.txt"], owned_before=before, root=merge_repo,
    )
    merge_errors = validate_repository_change_chain(
        [merged],
        expected_writer_scopes={"implementation": ["one.txt", "two.txt"]},
        expected_source_head=merge_head, root=merge_repo,
    )
    assert any("NONLINEAR_HISTORY" in error for error in merge_errors)


def test_repository_change_chain_rejects_mixed_dirty_and_committed_modes(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "mixed-modes"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "mixed@example.invalid")
    _git(repo, "config", "user.name", "Mixed Test")
    for path in ("one.txt", "two.txt"):
        (repo / path).write_text("before\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")
    baseline_head = _head(repo)
    task_digest = "sha256:" + "e" * 64
    scope = ["one.txt", "two.txt"]

    before = capture_repository(scope, root=repo)
    owned_before = capture_repository(["one.txt"], root=repo)
    (repo / "one.txt").write_text("dirty writer\n", encoding="utf-8")
    first = capture_repository_change(
        before=before, task_contract_digest=task_digest,
        node_id="implementation", role_id="E1", scope=["one.txt"],
        owned_before=owned_before, root=repo,
    )
    _git(repo, "add", "one.txt")
    _git(repo, "commit", "-qm", "commit dirty writer")
    before = capture_repository(scope, root=repo)
    owned_before = capture_repository(["two.txt"], root=repo)
    (repo / "two.txt").write_text("committed writer\n", encoding="utf-8")
    _git(repo, "add", "two.txt")
    _git(repo, "commit", "-qm", "committed writer")
    second = capture_repository_change(
        before=before, task_contract_digest=task_digest,
        node_id="docs_projection", role_id="TW", scope=["two.txt"],
        owned_before=owned_before, root=repo,
    )

    errors = validate_repository_change_chain(
        [first, second],
        expected_writer_scopes={
            "implementation": ["one.txt"], "docs_projection": ["two.txt"],
        },
        expected_source_head=baseline_head, root=repo,
    )
    assert any("mixes dirty and committed" in error for error in errors)
