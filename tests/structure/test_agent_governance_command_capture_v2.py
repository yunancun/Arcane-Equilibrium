"""Adversarial tests for the one-call governed command-capture Adapter."""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION = ROOT / "helper_scripts/maintenance_scripts"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

import agent_governance_command_capture_v2 as capture_v2  # noqa: E402
from agent_governance_capture_binding import collect_capture_evidence  # noqa: E402
from agent_governance_context import capture_repository_baseline  # noqa: E402
from agent_governance_execution import (  # noqa: E402
    compile_context,
    materialize_context_artifact,
)
from agent_governance_generation_summary import (  # noqa: E402
    capture_generation_summary,
)
from agent_governance_routing import route_task  # noqa: E402


def _review_context() -> tuple[dict, dict]:
    facts = {
        "task_shape": "review",
        "surfaces": ["python"],
        "risk": "medium",
        "uncertainty": "low",
        "objective": "verify one governed command capture",
        "scope": [
            "helper_scripts/maintenance_scripts/agent_governance_command_capture_v2.py"
        ],
        "dirty_scope": [
            "helper_scripts/maintenance_scripts/agent_governance_command_capture_v2.py"
        ],
        "acceptance_criteria": ["one readable, replayable command receipt"],
        "hard_stops": ["no runtime effect"],
        "baseline": capture_repository_baseline(),
        "direct_interfaces": ["command_capture_v2"],
        "previous_failure": "none",
    }
    routed = route_task(facts)
    plan = compile_context("E2", routed["task_facts"])
    return materialize_context_artifact(plan), routed


def _operations_verification_context() -> tuple[dict, dict]:
    verification_scope = [
        "helper_scripts/maintenance_scripts/runtime_environment_probe.py"
    ]
    facts = {
        "task_shape": "review",
        "surfaces": ["operations"],
        "risk": "medium",
        "uncertainty": "low",
        "side_effect_class": "none",
        "objective": "capture one bounded local runtime identity probe",
        "scope": verification_scope,
        "dirty_scope": [],
        "verification_scope": verification_scope,
        "acceptance_criteria": ["one exact read-only command receipt"],
        "hard_stops": ["no runtime mutation"],
        "baseline": capture_repository_baseline(),
        "direct_interfaces": ["runtime_environment_probe_v1"],
        "previous_failure": "no derived read-only path scope",
    }
    routed = route_task(facts)
    plan = compile_context("OPS", routed["task_facts"])
    return materialize_context_artifact(plan), routed


def _git_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "capture@example.invalid"],
        cwd=repository, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Capture Test"], cwd=repository,
        check=True,
    )
    (repository / "scope.txt").write_text("stable\n", encoding="utf-8")
    subprocess.run(["git", "add", "scope.txt"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repository, check=True)
    return repository


def _patch_test_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    task = {
        "node_id": "review", "role": "E2", "native_agent": "E2",
        "node_class": "verification", "permission": "read_only",
        "requires": [], "path_scope": ["scope.txt"],
    }
    monkeypatch.setattr(
        capture_v2, "_bound_execution_task",
        lambda _context, _native, _node, _root: (
            task,
            {"dirty_scope": ["scope.txt"]},
            ["scope.txt"],
        ),
    )
    monkeypatch.setattr(
        capture_v2, "authorize_native_command",
        lambda native, _command: {
            "allowed": True, "policy_class": "repo_or_local_test_read",
            "reason": "test fixture", "native_agent": native, "role_id": "E2",
            "node_class": "verification", "effective_permission": "read_only",
        },
    )


def test_absent_claims_are_canonical_false_and_live_facade_is_readable() -> None:
    artifact, routed = _review_context()
    contract = json.loads(artifact["canonical_plan"])["task_contract"]
    assert contract["runtime_claim"] is False
    assert contract["end_to_end_claim"] is False
    assert routed["task_facts"]["runtime_claim"] is False
    completed = subprocess.run(
        [
            sys.executable,
            "helper_scripts/maintenance_scripts/agent_governance.py",
            "capture-command", "--native-agent", "E2",
            "--node-id", "independent_review",
            "--context-artifact", json.dumps(artifact, separators=(",", ":")),
            "--", "git", "rev-parse", "--is-inside-work-tree",
        ],
        cwd=ROOT, check=False, capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    record = json.loads(completed.stdout)
    assert record["result"] == "PASS"
    assert record["stdout"]["encoding"] == "utf-8"
    assert record["stdout"]["preview_text"] == "true\n"
    assert record["effect_enforcement"] == "repository_policy_only"
    assert record["host_sandbox_attestation_ref"] is None


def test_native_node_and_dispatch_scope_are_derived_not_caller_asserted() -> None:
    artifact, _ = _review_context()
    with pytest.raises(PermissionError, match="does not own"):
        capture_v2._bound_execution_task(artifact, "QA", "independent_review", ROOT)
    with pytest.raises(ValueError, match="not one canonical"):
        capture_v2._bound_execution_task(artifact, "E2", "forged-node", ROOT)
    assert "path_scope" not in inspect.signature(
        capture_v2.capture_governed_command
    ).parameters


def test_verification_scope_binds_read_only_capture_and_closure_replay() -> None:
    artifact, routed = _operations_verification_context()
    task = next(
        item for item in routed["required_role_nodes"]
        if item["node_id"] == "ops_preflight"
    )
    assert task["path_scope"] == []
    record = capture_v2.capture_governed_command(
        native_agent="OPS",
        node_id="ops_preflight",
        context_artifact=artifact,
        argv=["git", "rev-parse", "--is-inside-work-tree"],
        root=ROOT,
    )
    verification_scope = [
        "helper_scripts/maintenance_scripts/runtime_environment_probe.py"
    ]
    assert record["execution_task"]["path_scope"] == []
    assert record["path_scope"] == verification_scope

    wrapper = {
        "id": "command:ops-runtime-probe",
        "scope": "test",
        "kind": "command_capture_v2",
        "digest": record["record_digest"],
        "artifact": record,
    }
    captured = collect_capture_evidence(
        [wrapper],
        expected_scope=[],
        expected_verification_scope=verification_scope,
        expected_source_head=subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            text=True, capture_output=True,
        ).stdout.strip(),
        expected_task_contract_digest=artifact["task_contract_digest"],
        expected_context_artifact_digest=artifact["artifact_digest"],
        require_current_repository=False,
        expected_execution_tasks={"ops_preflight": task},
    )
    assert captured["errors"] == []

    forged = collect_capture_evidence(
        [wrapper],
        expected_scope=[],
        expected_verification_scope=["helper_scripts/maintenance_scripts/other.py"],
        expected_source_head=subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            text=True, capture_output=True,
        ).stdout.strip(),
        expected_task_contract_digest=artifact["task_contract_digest"],
        expected_context_artifact_digest=artifact["artifact_digest"],
        require_current_repository=False,
        expected_execution_tasks={"ops_preflight": task},
    )
    assert any("path_scope differs" in error for error in forged["errors"])


def test_verification_scope_cannot_enable_writer_or_empty_capture_scope() -> None:
    writer_facts = {
        "task_shape": "implementation", "surfaces": ["python"],
        "risk": "low", "uncertainty": "low", "side_effect_class": "repo_write",
        "dirty_scope": ["src/owned.py"],
        "verification_scope": ["src/owned.py"],
        "task_prompt": "write only the owned source",
        "objective": "write only the owned source",
        "scope": ["src/owned.py"],
        "acceptance_criteria": ["source changed"],
        "hard_stops": ["no runtime effect"],
        "baseline": capture_repository_baseline(),
        "direct_interfaces": ["owned.py"],
        "previous_failure": "none",
    }
    routed = route_task(writer_facts)
    writer_artifact = materialize_context_artifact(
        compile_context("E1", routed["task_facts"])
    )
    with pytest.raises(PermissionError, match="restricted to read-only"):
        capture_v2._bound_execution_task(
            writer_artifact, "E1", "implementation", ROOT
        )

    scope_less_facts = {
        "task_shape": "review", "surfaces": ["operations"],
        "risk": "medium", "uncertainty": "low", "side_effect_class": "none",
        "dirty_scope": [], "task_prompt": "deny an unscoped runtime review",
        "objective": "deny an unscoped runtime review", "scope": ["runtime"],
        "acceptance_criteria": ["fail closed"],
        "hard_stops": ["no runtime mutation"],
        "baseline": capture_repository_baseline(),
        "direct_interfaces": ["runtime_environment_probe_v1"],
        "previous_failure": "none",
    }
    scope_less_route = route_task(scope_less_facts)
    scope_less_artifact = materialize_context_artifact(
        compile_context("OPS", scope_less_route["task_facts"])
    )
    with pytest.raises(ValueError, match="no non-empty derived path_scope"):
        capture_v2._bound_execution_task(
            scope_less_artifact, "OPS", "ops_preflight", ROOT
        )


def test_argv_is_shell_free_and_injection_text_is_literal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    _patch_test_binding(monkeypatch)
    marker = repository / "injected"
    record = capture_v2.capture_governed_command(
        native_agent="E2", node_id="review",
        context_artifact={
            "artifact_digest": "sha256:" + "a" * 64,
            "task_contract_digest": "sha256:" + "b" * 64,
        },
        argv=["/bin/echo", f"literal;touch {marker}"], root=repository,
    )
    assert record["result"] == "PASS"
    assert "literal;touch" in record["stdout"]["preview_text"]
    assert not marker.exists()


def test_whole_repository_digest_detects_mutation_outside_task_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    _patch_test_binding(monkeypatch)
    with pytest.raises(RuntimeError, match="mutated whole-repository generation"):
        capture_v2.capture_governed_command(
            native_agent="E2", node_id="review",
            context_artifact={
                "artifact_digest": "sha256:" + "a" * 64,
                "task_contract_digest": "sha256:" + "b" * 64,
            },
            argv=[
                sys.executable, "-c",
                "from pathlib import Path; Path('outside.txt').write_text('effect')",
            ],
            root=repository,
        )


def test_streaming_generation_binds_symlink_without_following_target(
    tmp_path: Path,
) -> None:
    repository = _git_repository(tmp_path)
    target = tmp_path / "outside-secret"
    target.write_text("first-secret", encoding="utf-8")
    os.symlink(target, repository / "untracked-link")
    before = capture_generation_summary(["."], root=repository)
    target.write_text("changed-secret", encoding="utf-8")
    after_target_change = capture_generation_summary(["."], root=repository)
    assert before["generation_digest"] == after_target_change["generation_digest"]
    (repository / "untracked-link").unlink()
    os.symlink("different-target", repository / "untracked-link")
    after_retarget = capture_generation_summary(["."], root=repository)
    assert before["generation_digest"] != after_retarget["generation_digest"]


def test_huge_output_is_streamed_bounded_and_directly_readable() -> None:
    executed = capture_v2._execute(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 1000000)"],
        root=ROOT, timeout_seconds=30, replay_contract="EXACT_OUTPUT",
    )
    stdout = executed["stdout"]
    assert stdout["bytes"] == 1_000_000
    assert stdout["preview_source_bytes"] == capture_v2.PREVIEW_LIMIT
    assert len(stdout["preview_text"].encode("utf-8")) <= capture_v2.PREVIEW_LIMIT
    assert stdout["truncated"] is True
    assert stdout["digest"].startswith("sha256:")


def test_secret_environment_is_removed_and_secret_preview_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_API_TOKEN", "ambient-token-must-not-leak")
    ambient = capture_v2._execute(
        [
            sys.executable, "-c",
            "import os; print(os.environ.get('FAKE_API_TOKEN', 'missing'))",
        ],
        root=ROOT, timeout_seconds=30, replay_contract="EXACT_OUTPUT",
    )
    assert ambient["stdout"]["preview_text"] == "missing\n"
    literal = capture_v2._execute(
        [sys.executable, "-c", "print('TOKEN=fake-secret-value')"],
        root=ROOT, timeout_seconds=30, replay_contract="EXACT_OUTPUT",
    )
    preview = literal["stdout"]["preview_text"]
    assert "fake-secret-value" not in preview
    assert preview == "TOKEN=<redacted>\n"
    assert literal["stdout"]["preview_redacted"] is True


def test_forged_scope_and_host_attestation_are_rejected() -> None:
    artifact, _ = _review_context()
    record = capture_v2.capture_governed_command(
        native_agent="E2", node_id="independent_review",
        context_artifact=artifact,
        argv=["git", "rev-parse", "--is-inside-work-tree"], root=ROOT,
    )
    forged_scope = deepcopy(record)
    forged_scope["path_scope"] = ["."]
    assert any(
        "path_scope differs" in error
        for error in capture_v2.validate_governed_command_capture(
            forged_scope,
            expected_path_scope=[
                "helper_scripts/maintenance_scripts/agent_governance_command_capture_v2.py"
            ],
        )
    )
    forged_attestation = deepcopy(record)
    forged_attestation["host_sandbox_attestation_ref"] = "self-report"
    assert any(
        "cannot self-assert" in error
        for error in capture_v2.validate_governed_command_capture(forged_attestation)
    )
