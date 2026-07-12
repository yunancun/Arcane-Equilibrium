"""Adversarial public-interface tests for governance evidence capture."""

from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_capture import (  # noqa: E402
    LOCAL_REPRODUCIBLE,
    ORCHESTRATOR_BOUND,
    PLATFORM_OR_EXTERNAL_ATTESTED,
    build_controller_workflow_call_record,
    build_unsigned_telemetry_record,
    capture_command,
    capture_repository,
    validate_command_capture,
    validate_repository_capture,
    validate_telemetry_record,
    validate_workflow_call_record,
)
from agent_governance_workflow_receipts import canonical_digest  # noqa: E402
from agent_governance_permissions import authorize_command  # noqa: E402
from agent_governance_capture_binding import collect_capture_evidence  # noqa: E402
from agent_governance_external_evidence import (  # noqa: E402
    validate_external_evidence_capture,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "capture@example.invalid")
    _git(repo, "config", "user.name", "Capture Test")
    (repo / "tracked.txt").write_text("before\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-qm", "fixture")
    return repo


def _external_capture() -> dict:
    excerpt = "Official policy text captured at the cited selector."
    record = {
        "schema_version": "external_evidence_capture_v1",
        "trust_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "capture_kind": "external_policy_snapshot",
        "url": "https://example.invalid/official-policy",
        "content_digest": "sha256:" + "a" * 64,
        "observed_at": "2026-07-11T10:00:00Z",
        "expires_at": "2026-07-12T10:00:00Z",
        "citation_ref": "citation:official-policy",
        "selector": "section-1",
        "excerpt": excerpt,
        "excerpt_digest": "sha256:" + hashlib.sha256(excerpt.encode()).hexdigest(),
    }
    canonical = json.dumps(
        record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    record["record_digest"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return record


def _resign_external(record: dict) -> dict:
    unsigned = {key: value for key, value in record.items() if key != "record_digest"}
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return {
        **unsigned,
        "record_digest": "sha256:" + hashlib.sha256(canonical).hexdigest(),
    }


def test_external_evidence_capture_requires_host_verifier_and_populates_typed_inventory() -> None:
    record = _external_capture()
    assert "external evidence capture lacks out-of-band host verification" in (
        validate_external_evidence_capture(
            record, adjudicated_at="2026-07-11T10:01:00Z"
        )
    )
    verifier = lambda candidate: candidate["record_digest"] == record["record_digest"]
    assert validate_external_evidence_capture(
        record, verifier=verifier, adjudicated_at="2026-07-11T10:01:00Z"
    ) == []
    wrapper = {
        "id": "external:official-policy", "scope": "external",
        "kind": "external_evidence_capture_v1", "digest": record["record_digest"],
        "observed_at": record["observed_at"], "expiry": record["expires_at"],
        "artifact": record,
    }
    captured = collect_capture_evidence(
        [wrapper], expected_scope=["tracked.txt"], expected_source_head="a" * 40,
        expected_task_contract_digest="sha256:" + "b" * 64,
        expected_context_artifact_digest="sha256:" + "c" * 64,
        require_current_repository=False, external_evidence_verifier=verifier,
        adjudicated_at="2026-07-11T10:01:00Z",
    )
    assert captured["errors"] == []
    assert captured["external_policy_attested"] == {"external:official-policy"}
    assert captured["external_evidence"]["external:official-policy"] == record

    forged_excerpt = deepcopy(record)
    forged_excerpt["excerpt"] = "A different claim."
    assert "external evidence capture excerpt digest is invalid" in (
        validate_external_evidence_capture(
            forged_excerpt, verifier=lambda _record: True,
            adjudicated_at="2026-07-11T10:01:00Z",
        )
    )


def test_external_evidence_default_adjudication_rejects_expired_and_future_capture() -> None:
    # default adjudication 以真實牆鐘為準;fixture 必須用相對時間,硬編碼日期會隨時間腐化
    def _iso(moment: datetime) -> str:
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")

    now = datetime.now(timezone.utc)
    expired = _resign_external({
        **_external_capture(),
        "observed_at": _iso(now - timedelta(days=2)),
        "expires_at": _iso(now - timedelta(days=1)),
    })
    assert "external evidence capture is stale at adjudication" in (
        validate_external_evidence_capture(expired, verifier=lambda _record: True)
    )
    future = _resign_external({
        **_external_capture(),
        "observed_at": _iso(now + timedelta(days=1)),
        "expires_at": _iso(now + timedelta(days=2)),
    })
    assert "external evidence capture is stale at adjudication" in (
        validate_external_evidence_capture(future, verifier=lambda _record: True)
    )


def test_repository_capture_contains_exact_scoped_git_generation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "tracked.txt").write_text("after\n", encoding="utf-8")
    untracked_bytes = b"new\x00bytes\n"
    (repo / "untracked.bin").write_bytes(untracked_bytes)

    capture = capture_repository(
        ["tracked.txt", "untracked.bin"], root=repo
    )

    assert capture["schema_version"] == "repository_capture_v1"
    assert capture["trust_tier"] == LOCAL_REPRODUCIBLE
    assert capture["source_head"] == _git(repo, "rev-parse", "HEAD")
    tracked_diff = base64.b64decode(capture["tracked_diff"]["content"])
    assert b"-before" in tracked_diff and b"+after" in tracked_diff
    assert capture["tracked_paths"] == ["tracked.txt"]
    assert len(capture["untracked"]) == 1
    assert base64.b64decode(capture["untracked"][0]["content"]) == untracked_bytes
    assert capture["changed_paths"] == ["tracked.txt", "untracked.bin"]
    assert validate_repository_capture(
        capture, expected_scope=["tracked.txt", "untracked.bin"]
    ) == []


def test_repository_capture_fails_closed_on_paths_tampering_and_staleness(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    capture = capture_repository(["tracked.txt"], root=repo)

    with pytest.raises(ValueError, match="escapes"):
        capture_repository(["../outside"], root=repo)
    with pytest.raises(ValueError, match="unsafe"):
        capture_repository(["*.txt"], root=repo)
    (repo / "linked").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink"):
        capture_repository(["linked/secret.txt"], root=repo)

    tampered = deepcopy(capture)
    tampered["tracked_diff"]["content"] = base64.b64encode(b"forged").decode("ascii")
    tampered["extra"] = True
    errors = validate_repository_capture(tampered)
    assert "repository capture fields do not match contract" in errors
    assert "tracked diff byte count is invalid" in errors
    assert "tracked diff digest is invalid" in errors
    assert "repository capture self-digest is invalid" in errors

    hidden_path = deepcopy(capture)
    hidden_path["changed_paths"] = ["tracked.txt"]
    assert "repository capture changed path manifest is inconsistent" in (
        validate_repository_capture(hidden_path)
    )

    (repo / "tracked.txt").write_text("next\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-qm", "advance")
    errors = validate_repository_capture(capture, root=repo, require_current=True)
    assert "repository capture is stale relative to the current Git generation" in errors


def test_command_capture_preflights_and_internally_records_real_execution(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    task_digest = "sha256:" + "a" * 64

    capture = capture_command(
        role_id="E2",
        node_id="source-verification",
        task_contract_digest=task_digest,
        command=["git", "status", "--short"],
        scope=["tracked.txt"],
        root=repo,
    )

    assert capture["schema_version"] == "command_capture_v1"
    assert capture["trust_tier"] == LOCAL_REPRODUCIBLE
    assert capture["authorization"]["allowed"] is True
    assert capture["replay_contract"] == "EXACT_OUTPUT"
    assert capture["argv"] == ["git", "status", "--short"]
    assert capture["exit_code"] == 0
    assert capture["result"] == "PASS"
    assert b"tracked.txt" in base64.b64decode(capture["stdout"]["content"])
    assert capture["repository_before"]["record_digest"]
    assert capture["repository_after"]["record_digest"]
    assert validate_command_capture(
        capture,
        expected_role_id="E2",
        expected_node_id="source-verification",
        expected_task_contract_digest=task_digest,
        expected_result="PASS",
    ) == []


def test_command_capture_rejects_injected_results_and_unsafe_commands(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    common = {
        "role_id": "E2",
        "node_id": "adversarial-review",
        "task_contract_digest": "sha256:" + "b" * 64,
        "scope": ["tracked.txt"],
        "root": repo,
    }

    assert not {
        "stdout",
        "stderr",
        "exit_code",
        "result",
        "started_at",
        "completed_at",
    } & set(inspect.signature(capture_command).parameters)
    with pytest.raises(TypeError, match="unexpected keyword argument 'stdout'"):
        capture_command(command=["git", "status"], stdout=b"forged", **common)  # type: ignore[call-arg]
    with pytest.raises(PermissionError, match="not authorized"):
        capture_command(command=["git", "commit", "-m", "forged"], **common)
    with pytest.raises(PermissionError, match="not authorized"):
        capture_command(command="git status; printf forged", **common)
    with pytest.raises(PermissionError, match="local-only"):
        capture_command(command=["ssh", "trade-core", "git status"], **common)

    capture = capture_command(command=["git", "status", "--short"], **common)
    tampered = deepcopy(capture)
    tampered["stdout"]["content"] = base64.b64encode(b"forged").decode("ascii")
    tampered["extra"] = "forged"
    errors = validate_command_capture(tampered)
    assert "command capture fields do not match contract" in errors
    assert "command stdout byte count is invalid" in errors
    assert "command stdout digest is invalid" in errors
    assert "command capture self-digest is invalid" in errors


def test_command_capture_pass_must_reproduce_and_e4_can_execute_local_tests(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    task_digest = "sha256:" + "9" * 64
    captured = capture_command(
        role_id="E2", node_id="independent-review",
        task_contract_digest=task_digest,
        command=["git", "status", "--short"], scope=["tracked.txt"], root=repo,
    )
    forged = deepcopy(captured)
    forged["argv"] = ["git", "diff", "--exit-code", "--", "tracked.txt"]
    forged["command"] = "git diff --exit-code -- tracked.txt"
    forged["authorization"] = authorize_command("E2", forged["command"])
    forged["exit_code"] = 0
    forged["timed_out"] = False
    forged["result"] = "PASS"
    forged["record_digest"] = canonical_digest(
        {key: value for key, value in forged.items() if key != "record_digest"}
    )
    errors = validate_command_capture(forged, root=repo, reexecute=True)
    assert "command capture claimed result does not reproduce under trusted local replay" in errors

    semantic_swap = deepcopy(captured)
    forged_stdout = b"substituted semantic output\n"
    semantic_swap["stdout"] = {
        "encoding": "base64",
        "content": base64.b64encode(forged_stdout).decode("ascii"),
        "bytes": len(forged_stdout),
        "digest": "sha256:" + __import__("hashlib").sha256(forged_stdout).hexdigest(),
    }
    semantic_swap["record_digest"] = canonical_digest(
        {key: value for key, value in semantic_swap.items() if key != "record_digest"}
    )
    assert (
        "command capture output does not reproduce under its trusted replay contract"
        in validate_command_capture(semantic_swap, root=repo, reexecute=True)
    )

    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    e4 = capture_command(
        role_id="E4", node_id="regression", task_contract_digest=task_digest,
        command=["python3", "-m", "pytest", "tests/test_ok.py", "-q"],
        scope=["tests/test_ok.py"], root=repo,
    )
    assert e4["node_class"] == "verification"
    assert e4["authorization"]["policy_class"] == "node_scoped_read_only"
    assert e4["replay_contract"] == "CANONICAL_TEST_OUTPUT_V1"
    assert validate_command_capture(
        e4, expected_role_id="E4", expected_result="PASS",
        root=repo, reexecute=True,
    ) == []


def test_workflow_call_record_is_canonical_and_strictly_bound() -> None:
    task_digest = "sha256:" + "c" * 64
    result_digest = "sha256:" + "d" * 64
    record = build_controller_workflow_call_record(
        workflow_contract_digest="sha256:" + "1" * 64,
        logical_call_id="call-019d",
        task_contract_digest=task_digest,
        node_id="e2-independent-review",
        payload_kind="review_fragment_v1",
        attempt=1,
        retry_parent_call_id=None,
        phase="Wave",
        label="e2-independent-review",
        requested={
            "logical_role": "E2", "platform": "claude_saved_workflow",
            "platform_requested_agent": "E2",
            "native_binding": {
                "logical_role": "E2", "native_agent": "E2",
                "node_class": "verification", "permission": "read_only",
            },
            "model": None,
            "effort": "high", "isolation": None,
            "node_class": "verification", "permission": "read_only",
        },
        prompt_digest="sha256:" + "e" * 64,
        context_artifact_digest="sha256:" + "2" * 64,
        dirty_scope_digest="sha256:" + "3" * 64,
        focus_digest="sha256:" + "4" * 64,
        compiler_input_tokens_lower_bound=100,
        admitted_input_tokens_lower_bound=120,
        response_schema_digest="sha256:" + "5" * 64,
        started_at="2026-07-11T12:00:00Z",
        ended_at="2026-07-11T12:01:00Z",
        returned_null=False,
        parsed_result_digest=result_digest,
    )

    assert record["schema_version"] == "workflow_call_record_v1"
    assert record["logical_call_id"] == "call-019d"
    assert record["requested"]["logical_role"] == "E2"
    assert record["requested"]["platform_requested_agent"] == "E2"
    assert validate_workflow_call_record(
        record,
        expected_call_id="call-019d",
        expected_task_contract_digest=task_digest,
        expected_context_artifact_digest="sha256:" + "2" * 64,
        expected_node_id="e2-independent-review",
        expected_role_id="E2",
        expected_result_digest=result_digest,
    ) == []

    for field, expected in (
        ("call_id", "call-other"),
        ("task_contract_digest", "sha256:" + "f" * 64),
        ("context_artifact_digest", "sha256:" + "6" * 64),
        ("node_id", "e4-verification"),
        ("role_id", "E4"),
        ("result_digest", "sha256:" + "0" * 64),
    ):
        kwargs = {f"expected_{field}": expected}
        assert any(
            "expected" in error
            for error in validate_workflow_call_record(record, **kwargs)
        )

    invalid_role = deepcopy(record)
    invalid_role["requested"]["logical_role"] = "invented-role"
    assert any(
        "registered delegated role" in error
        for error in validate_workflow_call_record(invalid_role)
    )

    legacy_shape = {
        "schema_version": "workflow_call_record_v1",
        "trust_tier": ORCHESTRATOR_BOUND,
        "assurance": "controller_known_metadata",
        "call_id": "call-019d",
        "result_digest": canonical_digest({"ok": True}),
    }
    assert "workflow call record fields do not match canonical contract" in (
        validate_workflow_call_record(legacy_shape)
    )


def test_telemetry_requires_exact_body_and_external_claims_fail_closed() -> None:
    metrics = {
        "input_tokens": 120,
        "output_tokens": 30,
        "cache_read_tokens": 60,
        "tool_calls": 4,
        "retry_count": 1,
        "wall_time_ms": 2500,
        "rework_count": 0,
    }
    record = build_unsigned_telemetry_record(
        subject_call_ids=["call-019d", "call-019e"],
        observed_at="2026-07-11T12:02:00Z",
        metrics=metrics,
    )

    assert record["trust_tier"] == ORCHESTRATOR_BOUND
    assert record["assurance"] == "unsigned_local_platform_record"
    assert validate_telemetry_record(
        record,
        expected_subject_call_ids=["call-019d", "call-019e"],
        expected_metrics=metrics,
        expected_assurance="unsigned_local_platform_record",
    ) == []

    random_digest_only = {"telemetry_digest": "sha256:" + "1" * 64}
    errors = validate_telemetry_record(random_digest_only)
    assert "telemetry record fields do not match contract" in errors
    assert "telemetry body is missing" in errors

    tampered = deepcopy(record)
    tampered["body"]["metrics"]["input_tokens"] = 999999
    errors = validate_telemetry_record(tampered)
    assert "telemetry body digest is invalid" in errors
    assert "telemetry record self-digest is invalid" in errors

    external_claim = deepcopy(record)
    external_claim["trust_tier"] = PLATFORM_OR_EXTERNAL_ATTESTED
    external_claim["assurance"] = "external_attested"
    external_claim["external_record"] = None
    errors = validate_telemetry_record(external_claim)
    assert "external telemetry requires a trusted platform record; unavailable" in errors
