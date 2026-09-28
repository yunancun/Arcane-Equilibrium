"""Exercise the real stdin/stdout hook boundary with native-shaped events."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "helper_scripts/maintenance_scripts/codex_subagent_guard.py"


def invoke(event):
    result = subprocess.run([sys.executable, str(SCRIPT)],
                            input=json.dumps(event), text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def root_event(tmp_path, tool="collaborationspawn_agent"):
    transcript = tmp_path / "root.jsonl"
    transcript.write_text(json.dumps({"type": "session_meta", "payload": {
        "id": "root-id", "source": "exec"}}) + "\n")
    return {"hook_event_name": "PreToolUse", "session_id": "root-id",
            "transcript_path": str(transcript), "tool_name": tool,
            "tool_input": {"agent_type": "E2", "task_name": "review", "fork_turns": "none"}}


@pytest.mark.parametrize("tool", [
    "collaborationspawn_agent", "collaboration.spawn_agent", "spawn_agent",
    "multi_agent_v1spawn_agent", "collaborationfollowup_task",
    "send_input", "resume_agent", "collaborationsend_message",
    "collaborationinterrupt_agent", "close_agent",
    "collaborationwait_agent", "collaborationlist_agents",
])
def test_actual_child_identity_denied_before_native_control(tool):
    event = {"hook_event_name": "PreToolUse", "tool_name": tool,
             "session_id": "parent-id", "agent_id": "child-id", "agent_type": "E2"}
    assert invoke(event)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_parent_can_dispatch_and_collect_results(tmp_path):
    for tool in ("collaborationspawn_agent", "collaborationwait_agent", "collaborationlist_agents"):
        assert invoke(root_event(tmp_path, tool)) == {}


def test_missing_agent_id_does_not_turn_child_into_parent(tmp_path):
    event = root_event(tmp_path)
    Path(event["transcript_path"]).write_text(json.dumps({"type": "session_meta", "payload": {
        "id": "child-id", "source": {"subagent": {"thread_spawn": {"parent_thread_id": "root-id"}}}}}))
    assert invoke(event)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("defect", ["missing", "wrong-id", "bad-json", "missing-file", "unknown-source"])
def test_unverified_root_is_denied(tmp_path, defect):
    event = root_event(tmp_path)
    if defect == "missing":
        del event["transcript_path"]
    elif defect == "wrong-id":
        event["session_id"] = "different-id"
    elif defect == "bad-json":
        Path(event["transcript_path"]).write_text("not json")
    elif defect == "unknown-source":
        Path(event["transcript_path"]).write_text(json.dumps({"type": "session_meta", "payload": {
            "id": "root-id", "source": "unknown"}}))
    else:
        Path(event["transcript_path"]).unlink()
    assert invoke(event)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_unrelated_tool_and_automatic_final_are_not_intercepted():
    assert invoke({"hook_event_name": "PreToolUse", "tool_name": "Bash", "agent_id": "child"}) == {}
    assert invoke({"hook_event_name": "SubagentStop", "agent_id": "child"}) == {}


def test_invalid_input_returns_a_native_deny_not_a_hook_error():
    assert invoke([])["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert invoke({"tool_name": "collaborationspawn_agent", "agent_id": "child"})[
        "hookSpecificOutput"]["permissionDecision"] == "deny"
    result = subprocess.run([sys.executable, str(SCRIPT)], input="{", text=True,
                            capture_output=True, check=True)
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
