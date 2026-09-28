"""Behavioral limits for the CLI entry, including real processes and signals."""
import copy
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "helper_scripts/maintenance_scripts"))
import codex_subagent_runner as runner


def binding():
    task = {"node_id": "review", "role": "E2", "native_agent": "E2",
            "node_class": "verification", "permission": "read_only", "requires": []}
    return {"task": task, "policy": {"max_call_attempts": 3, "max_wall_clock_ms": 60000}, "delivery": ["unit", "lane"],
            "frozen_contract": "contract-one", "dag": {"nodes": [task]}, "baseline": {"source_head": "first"}}


def test_unknown_parent_without_context_cannot_dispatch(tmp_path, monkeypatch):
    monkeypatch.delenv(runner.CHILD_MARKER, raising=False)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("no process permitted"))
    with pytest.raises(KeyError):
        runner.run(root=tmp_path, context={}, node_id="review", instruction="review",
                   output=tmp_path / "output", binary="codex")


def test_child_cannot_admit_itself_even_with_missing_context(tmp_path, monkeypatch):
    monkeypatch.setenv(runner.CHILD_MARKER, "1")
    with pytest.raises(PermissionError, match="CHILD_REENTRY_DENIED"):
        runner.bind(tmp_path, {}, "review")


def test_changed_generated_role_or_foreign_role_is_not_a_binding(tmp_path, monkeypatch):
    monkeypatch.delenv(runner.CHILD_MARKER, raising=False)
    task = binding()["task"]
    context = {"canonical_plan": json.dumps({"role": "E4", "execution_dag_binding": {"nodes": [task]}})}
    monkeypatch.setattr(runner, "_bound_execution_task", lambda *a: (task, {}, []))
    with pytest.raises(ValueError, match="role Context"):
        runner.bind(tmp_path, context, "review")


def test_duplicate_is_denied_across_output_directories(tmp_path):
    b = binding()
    state, first = runner.reserve(None, b, "controller", tmp_path, "review", None)
    first["status"] = "PASS"
    with pytest.raises(PermissionError, match="NODE_SPENT"):
        runner.reserve(state, b, "controller", tmp_path, "same work, different output", None)


@pytest.mark.parametrize("change", ["controller", "scope", "policy", "dag", "root"])
def test_changed_delivery_bindings_fail_before_spending(tmp_path, change):
    b = binding(); state, attempt = runner.reserve(None, b, "controller", tmp_path, "review", None)
    attempt["status"] = "FAIL"
    altered = copy.deepcopy(b); controller = "controller"; root = tmp_path
    if change == "controller": controller = "other"
    if change == "scope": altered["frozen_contract"] = "changed-scope"
    if change == "policy": altered["policy"]["max_call_attempts"] = 100
    if change == "dag": altered["dag"]["nodes"][0]["native_agent"] = "E4-verifier"
    if change == "root": root = tmp_path / "other"
    with pytest.raises(PermissionError, match="DELIVERY_BINDING_CHANGED"):
        runner.reserve(state, altered, controller, root, "review", attempt["id"])
    assert len(state["attempts"]) == 1


def test_one_explicit_failed_attempt_recheck_and_no_third(tmp_path):
    b = binding(); state, first = runner.reserve(None, b, "controller", tmp_path, "review", None)
    first["status"] = "UNVERIFIED"
    with pytest.raises(PermissionError, match="NODE_SPENT"):
        runner.reserve(state, b, "controller", tmp_path, "review", None)
    state, second = runner.reserve(state, b, "controller", tmp_path, "original blocker only", first["id"])
    second["status"] = "FAIL"
    with pytest.raises(PermissionError, match="NODE_SPENT"):
        runner.reserve(state, b, "controller", tmp_path, "again", second["id"])


def test_running_attempt_cannot_be_restarted_after_controller_loss(tmp_path):
    b = binding(); state, first = runner.reserve(None, b, "controller", tmp_path, "review", None)
    with pytest.raises(PermissionError, match="NODE_SPENT"):
        runner.reserve(state, b, "controller", tmp_path, "review", first["id"])


def test_delivery_deadline_is_not_refilled_by_fresh_context(tmp_path, monkeypatch):
    b = binding(); state, first = runner.reserve(None, b, "controller", tmp_path, "review", None)
    first["status"] = "FAIL"
    monkeypatch.setattr(runner.time, "time", lambda: state["started_at"] + 61)
    with pytest.raises(PermissionError, match="DELIVERY_DEADLINE"):
        runner.reserve(state, b, "controller", tmp_path, "review", first["id"])


def test_total_limit_is_not_refilled_by_another_node(tmp_path):
    b = binding(); b["policy"]["max_call_attempts"] = 1
    b["dag"]["nodes"].append(dict(b["task"], node_id="other"))
    state, first = runner.reserve(None, b, "controller", tmp_path, "review", None)
    first["status"] = "FAIL"; b["task"] = b["dag"]["nodes"][1]
    with pytest.raises(PermissionError, match="DELIVERY_CALL_LIMIT"):
        runner.reserve(state, b, "controller", tmp_path, "other review", None)


def test_failed_predecessor_blocks_successor(tmp_path):
    b = binding(); parent = dict(b["task"], node_id="correctness")
    b["task"]["requires"] = ["correctness"]; b["dag"]["nodes"].append(parent)
    with pytest.raises(PermissionError, match="PREDECESSOR_NOT_PASS"):
        runner.reserve(None, b, "controller", tmp_path, "regression", None)


def test_predecessor_pass_cannot_authorize_changed_source(tmp_path):
    b = binding(); successor = dict(b["task"], node_id="regression", requires=["review"])
    b["dag"]["nodes"].append(successor)
    state, first = runner.reserve(None, b, "controller", tmp_path, "review", None)
    first["status"] = "PASS"
    b["baseline"]["source_head"] = "repaired"; b["task"] = successor
    with pytest.raises(PermissionError, match="PREDECESSOR_NOT_PASS"):
        runner.reserve(state, b, "controller", tmp_path, "regression", None)
    assert len(state["attempts"]) == 1
    b["task"] = b["dag"]["nodes"][0]
    state, recheck = runner.reserve(state, b, "controller", tmp_path, "repair only", first["id"])
    recheck["status"] = "PASS"; b["task"] = successor
    runner.reserve(state, b, "controller", tmp_path, "regression", None)


def test_delivery_lock_excludes_second_process(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "git", lambda *a: str(tmp_path / "git-common"))
    with runner.delivery_lock(tmp_path, binding()):
        with pytest.raises(PermissionError, match="DELIVERY_BUSY"):
            with runner.delivery_lock(tmp_path, binding()):
                pytest.fail("second controller entered")


@pytest.mark.parametrize("source_changed,verdict,metadata,valid", [
    (False, "PASS", {}, True), (True, "PASS", {}, True), (False, None, {}, True),
    (False, "PASS", {"task_contract_digest": "contract", "role": "E2"}, True),
    (False, "PASS", {"evidence": {"context_artifact_digest": "context", "source_head": "head"}}, True),
    (False, "PASS", {"task_contract_digest": "sha256:5eab459ee4c771c9e96084e3969708e45b50a8313ccb61027c6272306a229ddc"}, False),
    (False, "PASS", {"role": "E4"}, False),
    (False, "PASS", {"native_agent": "E4-verifier"}, False),
    (False, "PASS", {"node_id": "other"}, False),
    (False, "PASS", {"source_head": "old"}, False),
    (False, "PASS", {"evidence": {"context_artifact_digest": "old-context"}}, False),
    (False, "PASS", {"evidence": {"context_digest": "old-context"}}, False),
    (False, "PASS", {"binding": {"task_contract_digest": None}}, False),
])
def test_result_requires_unchanged_source_and_explicit_verdict(tmp_path, monkeypatch, source_changed, verdict, metadata, valid):
    root = tmp_path / "repo"; root.mkdir()
    b = binding(); b.update(paths=["owned.py"], role={}, baseline={"source_head": "head"})
    b["policy"].update(max_call_duration_ms=300000, max_prompt_utf8_bytes_per_call=100000)
    context = {"shared_task_context_canonical": "task", "role_context_delta_canonical": "role",
               "artifact_digest": "context", "task_contract_digest": "contract"}
    monkeypatch.setenv("CODEX_THREAD_ID", "controller")
    monkeypatch.setattr(runner, "bind", lambda *a: b)
    monkeypatch.setattr(runner, "git", lambda *a: str(tmp_path / "git-common"))
    monkeypatch.setattr(runner, "capture_repository_baseline",
                        lambda *a: {"source_head": "changed" if source_changed else "head"})
    def fake_command(binary, root, output, role):
        code = "pass" if verdict is None else "from pathlib import Path; Path(" + repr(str(output / "verdict.txt")) + ").write_text(" + repr(json.dumps({"verdict": verdict, **metadata})) + ")"
        return [sys.executable, "-c", code]
    monkeypatch.setattr(runner, "command", fake_command)
    kwargs = dict(root=root, context=context, node_id="review", instruction="review", binary=sys.executable)
    result = runner.run(**kwargs, output=tmp_path / "first")
    assert result["status"] == ("PASS" if not source_changed and verdict and valid else "UNVERIFIED")
    if source_changed:
        assert result["error"] == "SOURCE_CHANGED_DURING_REVIEW"
    if not valid:
        assert "REVIEW_BINDING_MISMATCH" in result["error"]
        assert json.loads((tmp_path / "first/verdict.txt").read_text()) == {"verdict": verdict, **metadata}
        with runner.delivery_lock(root, b) as state_path:
            assert json.loads(state_path.read_text())["attempts"][-1]["status"] == "UNVERIFIED"
    with pytest.raises(PermissionError, match="NODE_SPENT"):
        runner.run(**kwargs, output=tmp_path / "other-output")
    assert not (tmp_path / "other-output").exists()


def test_correct_model_no_history_no_native_children_and_exact_scratch(tmp_path):
    argv = runner.command("/installed/codex", tmp_path / "repo", tmp_path / "output",
                          {"model": "gpt-6-sol", "model_reasoning_effort": "high", "developer_instructions": "E2"})
    assert argv[argv.index("--model") + 1] == "gpt-6-sol"
    assert "--ephemeral" in argv and "--ignore-user-config" in argv
    assert "resume" not in argv and "--dangerously-bypass-hook-trust" not in argv
    settings = [argv[i + 1] for i, a in enumerate(argv) if a == "-c"]
    for expected in ['features.multi_agent=false', 'features.multi_agent_v2=false', 'agents.enabled=false',
                     'permissions.tradebot-review.extends=":read-only"',
                     'permissions.tradebot-review.network.enabled=false', 'approval_policy="never"']:
        assert expected in settings
    writable = next(s for s in settings if s.startswith("permissions.tradebot-review.filesystem="))
    assert str(tmp_path / "output/scratch") in writable
    assert str(tmp_path / "repo") not in writable


def output_dir(tmp_path):
    out = tmp_path / "output"; out.mkdir(); (out / "scratch").mkdir()
    return out


def test_hard_deadline_handles_child_not_reading_stdin(tmp_path):
    out = output_dir(tmp_path)
    result = runner.execute([sys.executable, "-c", "import time; time.sleep(20)"],
                            "x" * 200000, out, tmp_path, 0.25)
    assert result["stop_reason"] == "DEADLINE"
    assert result["elapsed_seconds"] < 4
    assert result["exit_code"] != 0


def test_expired_deadline_does_not_read_unbounded_stderr(tmp_path, monkeypatch):
    out = output_dir(tmp_path)
    monkeypatch.setattr(Path, "read_text", lambda *a, **kw: pytest.fail("deadline must not read the whole log"))
    result = runner.execute([sys.executable, "-c", "import time; time.sleep(20)"], "", out, tmp_path, 0)
    assert result["stop_reason"] == "DEADLINE"
    assert result["elapsed_seconds"] < 3


def test_process_enumeration_failure_is_reported_and_leader_stops(tmp_path, monkeypatch):
    out = output_dir(tmp_path); marker = tmp_path / "unverified-descendant"
    child = "import time,pathlib; time.sleep(.7); pathlib.Path(" + repr(str(marker)) + ").touch()"
    parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "],start_new_session=True); time.sleep(20)"
    def failed_ps(*args, **kwargs):
        raise subprocess.TimeoutExpired("ps", 2)
    monkeypatch.setattr(subprocess, "check_output", failed_ps)
    result = runner.execute([sys.executable, "-c", parent], "", out, tmp_path, .2)
    assert result["stop_reason"] == "DEADLINE" and result["exit_code"] != 0
    assert result["cleanup_error"].startswith("DESCENDANT_CLEANUP_UNVERIFIED")
    time.sleep(.8)
    assert marker.exists()  # Separate finite child really survived: never claim complete cleanup.


@pytest.mark.skipif(sys.platform == "win32", reason="Unix process groups")
@pytest.mark.parametrize("separate_session", [False, True])
def test_deadline_terminates_spawned_descendant(tmp_path, separate_session):
    if separate_session:
        try:
            subprocess.check_output(["ps", "-axo", "pid=,ppid="], timeout=2, stderr=subprocess.PIPE)
        except (OSError, subprocess.SubprocessError):
            pytest.skip("controller process enumeration unavailable; requires separate host capture")
    out = output_dir(tmp_path); marker = tmp_path / "escaped"
    child = "import time,pathlib; time.sleep(1.1); pathlib.Path(" + repr(str(marker)) + ").touch()"
    parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "],start_new_session=" + repr(separate_session) + "); time.sleep(20)"
    result = runner.execute([sys.executable, "-c", parent], "", out, tmp_path, 0.2)
    assert result["stop_reason"] == "DEADLINE"
    time.sleep(1.2)
    assert not marker.exists()


def test_transport_failure_is_stopped_not_retried(tmp_path):
    out = output_dir(tmp_path)
    code = "import sys,time; sys.stderr.write('stream disconnected - retrying sampling request\\n'); sys.stderr.flush(); time.sleep(20)"
    result = runner.execute([sys.executable, "-c", code], "", out, tmp_path, 4)
    assert result["stop_reason"] == "TRANSPORT_FAILURE_NO_RETRY"
    assert result["elapsed_seconds"] < 3


def test_completed_process_retains_output(tmp_path):
    out = output_dir(tmp_path)
    result = runner.execute([sys.executable, "-c", "print('captured')"], "", out, tmp_path, 2)
    assert result["exit_code"] == 0 and result["stop_reason"] is None
    assert (out / "events.jsonl").read_text() == "captured\n"
