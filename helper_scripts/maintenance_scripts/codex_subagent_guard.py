#!/usr/bin/env python3
"""Deny native child delegation at PreToolUse; this does not admit parent work."""
from __future__ import annotations

import json
import sys
from pathlib import Path

CONTROL_TOOLS = frozenset({
    "spawn_agent", "followup_task", "resume_agent", "send_input",
    "send_message", "interrupt_agent", "close_agent", "wait_agent", "list_agents",
})
NAMESPACES = ("", "collaboration", "collaboration.", "multi_agent_v1", "multi_agent_v1.")
MAX_INPUT_BYTES = 1_048_576


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}


def decide(event: dict) -> dict:
    if not isinstance(event, dict):
        return deny("TRADEBOT_INVALID_HOOK_INPUT")
    if event.get("hook_event_name") == "SubagentStop":
        return {}
    if event.get("hook_event_name") != "PreToolUse":
        return deny("TRADEBOT_INVALID_HOOK_INPUT")
    name = event.get("tool_name")
    if name not in {prefix + tool for prefix in NAMESPACES for tool in CONTROL_TOOLS}:
        return {}
    if event.get("agent_id"):
        return deny("TRADEBOT_NO_RECURSIVE_DISPATCH: return the assigned result to the parent conductor.")

    # Hooks may inherit the launching desktop's CODEX_THREAD_ID, so that
    # environment variable is not caller identity. Missing child metadata
    # must not silently turn a child into the parent.
    try:
        session_id, transcript = event["session_id"], event["transcript_path"]
        if not isinstance(session_id, str) or not session_id or not isinstance(transcript, str):
            raise ValueError("missing identity")
        with Path(transcript).open("rb") as stream:
            line = stream.readline(MAX_INPUT_BYTES + 1)
        if len(line) > MAX_INPUT_BYTES:
            raise ValueError("oversized metadata")
        first = json.loads(line)
        metadata = first["payload"]
        source = metadata["source"]
        root = (first.get("type") == "session_meta"
                and metadata.get("id") == session_id
                and source in ("exec", "cli", "vscode"))
        if root:
            return {}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return deny("TRADEBOT_CALLER_UNVERIFIED: native dispatch requires a verifiable root caller.")


def main() -> None:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        result = (deny("TRADEBOT_INVALID_HOOK_INPUT") if len(raw) > MAX_INPUT_BYTES
                  else decide(json.loads(raw)))
    except (ValueError, TypeError, AttributeError):
        result = deny("TRADEBOT_INVALID_HOOK_INPUT")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
