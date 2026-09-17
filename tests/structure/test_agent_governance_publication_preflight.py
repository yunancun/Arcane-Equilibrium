from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[2] / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import git_publication_preflight as preflight  # noqa: E402
from agent_governance_context import capture_repository_baseline  # noqa: E402
from agent_governance_routing import route_task, task_contract_projection  # noqa: E402
from agent_governance_task_admission import (  # noqa: E402
    FileTaskAdmissionStore, acquire_task_admission, release_task_admission,
)
from agent_governance_writer_lease import inspect_worktree  # noqa: E402


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.PIPE,
    ).strip()


def commit(repo: Path, path: str, content: str) -> str:
    (repo / path).write_text(content)
    git(repo, "add", "--", path)
    git(repo, "commit", "-qm", "fixture change")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def case(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "Fixture")
    base = commit(repo, "owned.txt", "base\n")
    git(repo, "remote", "add", "origin", "https://github.com/example/project.git")
    git(repo, "update-ref", "refs/remotes/origin/main", base)
    feature = tmp_path / "feature"
    git(repo, "worktree", "add", "-qb", "agent/preflight", str(feature), base)
    monkeypatch.setattr(preflight, "native_remote_head", lambda *args: base)
    return {
        "repo": feature, "expected_branch": "agent/preflight", "expected_head": base,
        "admission_base": base, "allow_paths": ["owned.txt"],
        "work_item_id": "PREFLIGHT-TEST", "lane_id": "publication", "owner": "pytest",
    }


def changed(case):
    case["expected_head"] = commit(case["repo"], "owned.txt", "feature\n")
    return case


def admit(case):
    facts = route_task({
        "task_shape": "implementation", "surfaces": ["python", "agent_workflow"],
        "risk": "low", "uncertainty": "low", "side_effect_class": "repo_write",
        "objective": "Preflight fixture", "scope": ["owned.txt"],
        "dirty_scope": ["owned.txt"], "verification_scope": ["owned.txt"],
        "acceptance_criteria": ["Diagnose without mutation"],
        "hard_stops": ["No external effects"], "task_prompt": "Test the diagnostic",
        "baseline": capture_repository_baseline(case["repo"]),
        "direct_interfaces": ["owned.txt"], "previous_failure": "none",
        "work_item_id": case["work_item_id"], "lane_id": case["lane_id"],
    })["task_facts"]
    result = acquire_task_admission(
        repo=case["repo"], task_id="preflight-test", owner="pytest",
        task_contract=task_contract_projection(facts),
    )
    assert result["status"] == "PASS", result.get("reasons")
    return result


def snapshot(repo):
    common = inspect_worktree(repo).common_dir
    return {str(p.relative_to(common)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in common.rglob("*") if p.is_file()}


def test_new_delivery_reports_full_range_without_writes(case):
    changed(case)
    before = snapshot(case["repo"])
    result = preflight.inspect_publication(**case)
    assert result["status"] == "READ_ONLY_READY"
    assert result["published_main"] == case["admission_base"]
    assert result["commits"][0]["commit"] == case["expected_head"]
    assert result["touched_paths"] == ["owned.txt"]
    assert result["lifecycle"]["state"] == "NEW_DELIVERY"
    assert result["publication_authorized"] is False
    assert result["mutated_local"] is result["mutated_remote"] is False
    assert result["coverage_debt"]
    assert before == snapshot(case["repo"])


def test_matching_active_admission_is_reused_not_readmitted(case):
    admitted = admit(case)
    changed(case)
    before = snapshot(case["repo"])
    result = preflight.inspect_publication(**case)
    assert result["status"] == "READ_ONLY_READY"
    assert result["lifecycle"]["accepted_base"] == case["admission_base"]
    assert "Keep the matching admission" in result["next_steps"][0]
    assert admitted["admission_id"] not in json.dumps(result)
    assert before == snapshot(case["repo"])


def test_released_delivery_and_empty_range_report_both_root_causes(case):
    admitted = admit(case)
    changed(case)
    released = release_task_admission(
        repo=case["repo"], task_id="preflight-test", owner="pytest",
        admission_id=admitted["admission_id"],
    )
    assert released["status"] == "PASS"
    case["admission_base"] = case["expected_head"]
    before = snapshot(case["repo"])
    result = preflight.inspect_publication(**case)
    assert {"DELIVERY_REPAIR_NOT_AUTHORIZED", "ORDINARY_PUBLICATION_EMPTY_COMMIT_RANGE",
            "ADMISSION_BASE_NOT_PUBLISHED_MAIN"}.issubset(result["reasons"])
    assert result["lifecycle"]["state"] == "RELEASED_DELIVERY"
    assert any("do not reset" in step for step in result["next_steps"])
    assert any("Preserve the reviewed checkout" in step for step in result["next_steps"])
    assert admitted["admission_id"] not in json.dumps(result)
    assert before == snapshot(case["repo"])


@pytest.mark.parametrize("mode,reason", [
    ("owner", "DELIVERY_OWNER_CHANGED"),
    ("base", "ADMISSION_BASE_MISMATCH"),
    ("scope", "DELIVERY_SCOPE_EXPANDED"),
    ("missing-state", "DELIVERY_STATE_AMBIGUOUS"),
    ("corrupt-journal", "LOCAL_EVIDENCE_UNAVAILABLE_OR_AMBIGUOUS"),
])
def test_lifecycle_mismatches_fail_closed(case, mode, reason):
    admit(case)
    changed(case)
    store = FileTaskAdmissionStore(inspect_worktree(case["repo"]).common_dir)
    if mode == "owner":
        case["owner"] = "different-owner"
    elif mode == "base":
        case["admission_base"] = case["expected_head"]
    elif mode == "scope":
        case["allow_paths"].append("outside.txt")
    elif mode == "missing-state":
        store.state_path.unlink()
    else:
        store.delivery_path.write_text("{}")
    before = snapshot(case["repo"])
    assert reason in preflight.inspect_publication(**case)["reasons"]
    assert before == snapshot(case["repo"])


@pytest.mark.parametrize("url", [
    "/tmp/local.git", "https://token@github.com/example/project.git",
    "https://github.com.evil.invalid/example/project.git", "git@github.com:example/project.git",
])
def test_unsafe_origin_never_calls_remote_or_leaks_url(case, monkeypatch, url):
    changed(case)
    git(case["repo"], "remote", "set-url", "origin", url)
    def forbidden(*args):
        pytest.fail("unsafe origin called remote producer")
    monkeypatch.setattr(preflight, "native_remote_head", forbidden)
    result = preflight.inspect_publication(**case)
    assert "UNSAFE_ORIGIN" in result["reasons"]
    assert url not in json.dumps(result)


@pytest.mark.parametrize("config_key", ["remote.origin.url", "remote.origin.pushurl"])
def test_multiple_or_different_origin_rejected_before_remote(case, monkeypatch, config_key):
    changed(case)
    git(case["repo"], "config", "--add", config_key, "https://github.com/other/project.git")
    monkeypatch.setattr(preflight, "native_remote_head", lambda *args: pytest.fail("remote called"))
    assert "UNSAFE_ORIGIN" in preflight.inspect_publication(**case)["reasons"]


def test_unavailable_remote_and_tracking_staleness(case, monkeypatch):
    changed(case)
    monkeypatch.setattr(preflight, "native_remote_head", lambda *args: None)
    assert "PUBLISHED_MAIN_UNAVAILABLE" in preflight.inspect_publication(**case)["reasons"]
    monkeypatch.setattr(preflight, "native_remote_head", lambda *args: case["admission_base"])
    git(case["repo"], "update-ref", "refs/remotes/origin/main", case["expected_head"])
    assert "REMOTE_TRACKING_STALE" in preflight.inspect_publication(**case)["reasons"]


def test_dirty_wrong_head_and_branch_are_blockers(case):
    changed(case)
    (case["repo"] / "unknown.txt").write_text("preserve me")
    case["expected_head"] = case["admission_base"]
    case["expected_branch"] = "agent/different"
    result = preflight.inspect_publication(**case)
    assert {"DIRTY_WORKTREE", "HEAD_MISMATCH", "BRANCH_MISMATCH"}.issubset(result["reasons"])
    assert (case["repo"] / "unknown.txt").read_text() == "preserve me"


def test_mid_probe_head_drift_is_detected(case, monkeypatch):
    changed(case)
    def drift(*args):
        commit(case["repo"], "owned.txt", "changed during remote read\n")
        return case["admission_base"]
    monkeypatch.setattr(preflight, "native_remote_head", drift)
    assert "PREFLIGHT_STATE_CHANGED" in preflight.inspect_publication(**case)["reasons"]


def test_intermediate_revert_cannot_hide_scope_violation(case):
    changed(case)
    commit(case["repo"], "outside.txt", "forbidden\n")
    git(case["repo"], "revert", "--no-edit", "HEAD")
    case["expected_head"] = git(case["repo"], "rev-parse", "HEAD")
    result = preflight.inspect_publication(**case)
    assert len(result["commits"]) == 3
    assert result["out_of_scope_paths"] == ["outside.txt"]
    assert "COMMIT_RANGE_OUT_OF_SCOPE" in result["reasons"]


def test_rename_requires_both_literal_paths(case):
    git(case["repo"], "mv", "owned.txt", "renamed.txt")
    git(case["repo"], "commit", "-qm", "rename")
    case["expected_head"] = git(case["repo"], "rev-parse", "HEAD")
    case["allow_paths"] = ["renamed.txt"]
    result = preflight.inspect_publication(**case)
    assert result["touched_paths"] == ["owned.txt", "renamed.txt"]
    assert result["out_of_scope_paths"] == ["owned.txt"]


def test_nonlinear_range_is_rejected(case):
    changed(case)
    git(case["repo"], "checkout", "-qb", "side", case["admission_base"])
    commit(case["repo"], "side.txt", "side\n")
    git(case["repo"], "checkout", "-q", "agent/preflight")
    git(case["repo"], "merge", "--no-ff", "-qm", "merge", "side")
    case["expected_head"] = git(case["repo"], "rev-parse", "HEAD")
    assert "NATIVE_COMMIT_RANGE_NONLINEAR_HISTORY" in preflight.inspect_publication(**case)["reasons"]


@pytest.mark.parametrize("field,value", [
    ("expected_head", "HEAD"), ("admission_base", "--all"),
    ("expected_branch", "main"), ("allow_paths", ["../outside"]),
    ("allow_paths", ["directory/"]), ("work_item_id", ""),
])
def test_invalid_input_has_no_remote_callbacks(case, monkeypatch, field, value):
    case[field] = value
    monkeypatch.setattr(preflight, "native_remote_head", lambda *args: pytest.fail("remote called"))
    assert preflight.inspect_publication(**case)["status"] == "BLOCKED"


def cli_args(case):
    args = []
    for key, value in case.items():
        if key == "allow_paths":
            for path in value:
                args.extend(["--allow-path", path])
        else:
            args.extend(["--" + key.replace("_", "-"), str(value)])
    return args


def test_cli_json_human_and_exit_codes(case, capsys):
    changed(case)
    assert preflight.main(cli_args(case)) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "READ_ONLY_READY"
    assert preflight.main(cli_args(case) + ["--human"]) == 0
    assert "publication_authorized=false" in capsys.readouterr().out
    case["admission_base"] = case["expected_head"]
    assert preflight.main(cli_args(case)) == 3
    assert "ORDINARY_PUBLICATION_EMPTY_COMMIT_RANGE" in json.loads(capsys.readouterr().out)["reasons"]


def test_public_subprocess_entrypoint_is_read_only(case):
    changed(case)
    git(case["repo"], "remote", "set-url", "origin", "/tmp/never-contact")
    before = snapshot(case["repo"])
    completed = subprocess.run(
        [sys.executable, str(HELPERS / "git_publication_preflight.py"), *cli_args(case)],
        text=True, capture_output=True, timeout=20,
    )
    assert completed.returncode == 3
    assert "UNSAFE_ORIGIN" in json.loads(completed.stdout)["reasons"]
    assert before == snapshot(case["repo"])
