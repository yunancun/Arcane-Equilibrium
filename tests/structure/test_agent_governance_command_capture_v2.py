"""Adversarial tests for the one-call governed command-capture Adapter."""

from __future__ import annotations

import inspect
import io
import json
import os
import subprocess
import sys
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION = ROOT / "helper_scripts/maintenance_scripts"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

import agent_governance_command_capture_v2 as capture_v2  # noqa: E402
import agent_governance as governance  # noqa: E402
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


def test_absent_claims_are_canonical_false_and_live_facade_is_readable(
    tmp_path: Path,
) -> None:
    artifact, routed = _review_context()
    contract = json.loads(artifact["canonical_plan"])["task_contract"]
    assert contract["runtime_claim"] is False
    assert contract["end_to_end_claim"] is False
    assert routed["task_facts"]["runtime_claim"] is False
    # context artifact 以 @file 傳入(AGENTS.md / 各 role card 的 canonical 慣例),
    # 不塞進單一 argv 元素;否則隨 registry 成長,序列化 JSON 會超過 Linux
    # execve 的 MAX_ARG_STRLEN(128 KiB)單參數上限而觸發 E2BIG。
    context_file = tmp_path / "context.json"
    context_file.write_text(
        json.dumps(artifact, separators=(",", ":")), encoding="utf-8"
    )
    completed = subprocess.run(
        [
            sys.executable,
            "helper_scripts/maintenance_scripts/agent_governance.py",
            "capture-command", "--native-agent", "E2",
            "--node-id", "independent_review",
            "--context-artifact", f"@{context_file}",
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


def test_full_w0_default_capture_ceiling_is_bounded_600_seconds() -> None:
    assert (
        inspect.signature(capture_v2.capture_governed_command)
        .parameters["timeout_seconds"]
        .default
        == 600
    )
    parsed = governance._build_parser().parse_args([
        "capture-command",
        "--native-agent",
        "E2",
        "--node-id",
        "review",
        "--context-artifact",
        "{}",
        "--",
        "git",
        "status",
    ])
    assert parsed.timeout_seconds == 600


def test_verification_scope_binds_read_only_capture_and_closure_replay() -> None:
    artifact, routed = _operations_verification_context()
    task = next(
        item for item in routed["required_role_nodes"]
        if item["node_id"] == "ops_observation"
    )
    assert task["path_scope"] == []
    record = capture_v2.capture_governed_command(
        native_agent="OPS",
        node_id="ops_observation",
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
        expected_execution_tasks={"ops_observation": task},
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
        expected_execution_tasks={"ops_observation": task},
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
            scope_less_artifact, "OPS", "ops_observation", ROOT
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


def test_controlled_pytest_environment_uses_only_bound_provider_capsule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_capsule = tmp_path / "provider-capsule"
    caller_site = tmp_path / "caller-selected-site"
    for path in (provider_capsule, caller_site):
        path.mkdir()
    monkeypatch.setenv("PYTHONPATH", str(caller_site))

    pytest_isolation = tmp_path / "pytest-isolation"
    pytest_isolation.mkdir()
    pytest_environment = capture_v2._controlled_environment(
        pytest_isolation,
        argv=[
            *capture_v2.GOVERNED_PYTEST_PREFIX,
            *capture_v2.GOVERNED_PYTEST_REQUIRED_ARGS,
            "-q",
            "tests/test_one.py",
        ],
        pytest_provider=provider_capsule,
    )
    assert pytest_environment["PYTHONPATH"] == str(provider_capsule)
    assert str(caller_site) not in pytest_environment["PYTHONPATH"]
    assert pytest_environment["PYTHONNOUSERSITE"] == "1"
    assert pytest_environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert pytest_environment["PYTHONSAFEPATH"] == "1"

    read_only_isolation = tmp_path / "read-only-isolation"
    read_only_isolation.mkdir()
    read_only_environment = capture_v2._controlled_environment(
        read_only_isolation,
        argv=["git", "rev-parse", "HEAD"],
    )
    assert "PYTHONPATH" not in read_only_environment


def test_closed_command_capture_schema_requires_nullable_provider_field() -> None:
    schema = json.loads(
        (ROOT / ".codex/schemas/closure_packet_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    command_capture = schema["$defs"]["commandCaptureV2"]

    assert "pytest_provider" in command_capture["required"]
    assert command_capture["properties"]["pytest_provider"] == {
        "anyOf": [
            {"$ref": "#/$defs/governedPytestProvider"},
            {"type": "null"},
        ]
    }


def test_nested_capture_recovers_code_owned_pytest_provider(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "test_nested_provider.py"
    probe.write_text("def test_nested_provider():\n    assert True\n")
    code = (
        "import sys;"
        f"sys.path.insert(0,{str(IMPLEMENTATION)!r});"
        "import agent_governance_command_capture_v2 as capture;"
        "result=capture._execute("
        "[*capture.GOVERNED_PYTEST_PREFIX,"
        "*capture.GOVERNED_PYTEST_REQUIRED_ARGS,'-q',"
        f"{str(probe)!r}],"
        f"root=__import__('pathlib').Path({str(ROOT)!r}),"
        "timeout_seconds=30,replay_contract='CANONICAL_TEST_OUTPUT_V1');"
        "print(result['result'],result['exit_code'])"
    )
    outer = capture_v2._execute(
        [sys.executable, "-c", code],
        root=ROOT,
        timeout_seconds=45,
        replay_contract="EXACT_OUTPUT",
    )
    assert outer["result"] == "PASS"
    assert outer["stdout"]["preview_text"] == "PASS 0\n"


def test_governed_pytest_bootstrap_rejects_candidate_provider_injection(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "candidate"
    repo.mkdir()
    marker = tmp_path / "provider-injection-marker"
    poison = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "raise RuntimeError('candidate provider injection executed')\n"
    )
    (repo / "pytest.py").write_text(poison, encoding="utf-8")
    (repo / "sitecustomize.py").write_text(poison, encoding="utf-8")
    (repo / "conftest.py").write_text(poison, encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        "addopts = '-p candidate_plugin'\n",
        encoding="utf-8",
    )
    (repo / "candidate_plugin.py").write_text(poison, encoding="utf-8")
    (repo / "packaging.py").write_text(poison, encoding="utf-8")
    probe = repo / "test_real.py"
    probe.write_text("def test_real():\n    assert True\n", encoding="utf-8")
    result = capture_v2._execute(
        [
            *capture_v2.GOVERNED_PYTEST_PREFIX,
            *capture_v2.GOVERNED_PYTEST_REQUIRED_ARGS,
            "-q",
            str(probe),
        ],
        root=repo,
        timeout_seconds=30,
        replay_contract="CANONICAL_TEST_OUTPUT_V1",
    )
    assert result["result"] == "PASS"
    assert marker.exists() is False
    assert result["pytest_provider"]["provider_stable"] is True
    assert result["pytest_provider"]["project_config_loading_disabled"] is True
    assert result["pytest_provider"]["test_import_path_appended"] is True
    assert result["pytest_provider"]["repository_root_fixed"] is True
    assert capture_v2._pytest_provider_errors(
        result["pytest_provider"],
        argv=[
            *capture_v2.GOVERNED_PYTEST_PREFIX,
            *capture_v2.GOVERNED_PYTEST_REQUIRED_ARGS,
            "-q",
            str(probe),
        ],
    ) == []


def test_governed_pytest_requires_the_code_owned_git_provider_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = tmp_path / "test_provider_admission.py"
    probe.write_text(
        "def test_provider_admission():\n    assert True\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        capture_v2,
        "GOVERNED_PYTEST_PROVIDER_LOCK_PATH",
        ".codex/providers/governed_pytest_v1/missing-lock.json",
    )

    result = capture_v2._execute(
        [
            *capture_v2.GOVERNED_PYTEST_PREFIX,
            *capture_v2.GOVERNED_PYTEST_REQUIRED_ARGS,
            "-q",
            str(probe),
        ],
        root=ROOT,
        timeout_seconds=30,
        replay_contract="CANONICAL_TEST_OUTPUT_V1",
    )

    assert result["result"] == "FAIL"
    assert result["exit_code"] == 127
    assert "code-owned Git blob" in result["stderr"]["preview_text"]
    assert result["pytest_provider"] is None


@pytest.mark.parametrize("unsafe_member", ["../escape.py", "inject.pth"])
def test_code_owned_provider_rejects_unsafe_wheel_members(
    tmp_path: Path, unsafe_member: str,
) -> None:
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(unsafe_member, "raise RuntimeError('executed')\n")

    with pytest.raises(ValueError, match="wheel member is unsafe"):
        capture_v2._extract_provider_wheels(
            capsule,
            [(
                {
                    "path": (
                        ".codex/providers/governed_pytest_v1/wheels/"
                        "unsafe-1-py3-none-any.whl"
                    )
                },
                payload.getvalue(),
            )],
        )
    assert not (tmp_path / "escape.py").exists()


def test_governed_provider_identity_binds_the_exact_reviewed_head(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "test_provider_head.py"
    probe.write_text(
        "def test_provider_head():\n    assert True\n",
        encoding="utf-8",
    )
    argv = [
        *capture_v2.GOVERNED_PYTEST_PREFIX,
        *capture_v2.GOVERNED_PYTEST_REQUIRED_ARGS,
        "-q",
        str(probe),
    ]
    result = capture_v2._execute(
        argv,
        root=ROOT,
        timeout_seconds=30,
        replay_contract="CANONICAL_TEST_OUTPUT_V1",
    )
    assert result["result"] == "PASS"
    assert any(
        "differs from the exact reviewed repository head" in error
        for error in capture_v2._pytest_provider_errors(
            result["pytest_provider"],
            argv=argv,
            expected_source_head="0" * 40,
        )
    )


def test_plain_pytest_argv_is_rejected_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    _patch_test_binding(monkeypatch)
    with pytest.raises(PermissionError, match="no-site governed bootstrap"):
        capture_v2.capture_governed_command(
            native_agent="E2",
            node_id="review",
            context_artifact={
                "artifact_digest": "sha256:" + "a" * 64,
                "task_contract_digest": "sha256:" + "b" * 64,
            },
            argv=["python3", "-m", "pytest", "-q", "scope.txt"],
            root=repository,
        )


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
