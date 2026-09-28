#!/usr/bin/env python3
"""One finite, read-only Codex review call; PM retains the existing workflow DAG."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from agent_governance_command_capture_v2 import _bound_execution_task
from agent_governance_context import capture_repository_baseline
from agent_governance_registry import load_registry, render_views


CHILD_MARKER = "TRADEBOT_CLI_REVIEW_CHILD"


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def bind(root: Path, context: dict, node_id: str) -> dict:
    """Use the existing Context verifier and exact native-node permission binding."""
    if os.environ.get(CHILD_MARKER):
        raise PermissionError("CHILD_REENTRY_DENIED")
    plan = json.loads(context["canonical_plan"])
    nodes = [n for n in plan["execution_dag_binding"]["nodes"] if n["node_id"] == node_id]
    if len(nodes) != 1:
        raise ValueError("node is absent or ambiguous")
    task, contract, paths = _bound_execution_task(context, nodes[0]["native_agent"], node_id, root)
    if plan["role"] != task["role"]:
        raise ValueError("role Context does not belong to this node")
    if not contract.get("work_item_id") or not contract.get("lane_id"):
        raise ValueError("controller-owned work_item_id and lane_id are required")
    if git(root, "status", "--porcelain"):
        raise ValueError("commit the approved local source checkpoint before review")
    registry = load_registry(root / ".codex/agent_registry_v1.json")
    role_path = root / ".codex/agents" / (task["native_agent"] + ".toml")
    rendered = render_views(registry, root)[role_path]
    if role_path.read_text() != rendered:
        raise ValueError("generated role differs from Registry")
    role = tomllib.loads(rendered)
    try:
        subprocess.check_output(["ps", "-axo", "pid=,ppid="], timeout=2, stderr=subprocess.PIPE)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PermissionError("CONTROLLER_PROCESS_MONITOR_UNAVAILABLE") from exc
    frozen = {k: v for k, v in contract.items() if k not in {"baseline", "previous_failure"}}
    return {"task": task, "contract": contract, "paths": paths, "role": role,
            "policy": json.loads(context["budget_authority_canonical"]),
            "delivery": [contract["work_item_id"], contract["lane_id"]],
            "frozen_contract": digest(frozen), "dag": plan["execution_dag_binding"],
            "baseline": capture_repository_baseline(root)}


@contextmanager
def delivery_lock(root: Path, binding: dict):
    """Retain spent attempts across processes/output folders; no automatic reset."""
    common = Path(git(root, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = root / common
    directory = common.resolve() / "codex-cli-reviews" / digest(binding["delivery"])
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(directory / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PermissionError("DELIVERY_BUSY: one active review per delivery") from exc
        yield directory / "state.json"


def reserve(state: dict | None, binding: dict, controller: str,
            root: Path, instruction: str, recheck_of: str | None) -> tuple[dict, dict]:
    policy = binding["policy"]
    node = binding["task"]["node_id"]
    frozen = {"controller": controller, "root": str(root),
              "contract": binding["frozen_contract"], "dag": digest(binding["dag"]),
              "policy": digest(policy)}
    if state is None:
        state = {"binding": frozen, "started_at": time.time(), "attempts": []}
    if state["binding"] != frozen:
        raise PermissionError("DELIVERY_BINDING_CHANGED")
    age = time.time() - state["started_at"]
    if not 0 <= age < policy["max_wall_clock_ms"] / 1000:
        raise PermissionError("DELIVERY_DEADLINE")
    attempts = state["attempts"]
    prior = [a for a in attempts if a["node_id"] == node]
    generation = digest(binding["baseline"])
    if len(attempts) >= policy["max_call_attempts"]:
        raise PermissionError("DELIVERY_CALL_LIMIT")
    if prior:
        if (len(prior) >= 2 or recheck_of != prior[-1]["id"]
                or prior[-1]["status"] == "RUNNING"
                or (prior[-1]["status"] == "PASS"
                    and prior[-1].get("source_generation") == generation)):
            raise PermissionError("NODE_SPENT: no automatic duplicate, retry or resume")
    elif recheck_of is not None:
        raise PermissionError("recheck must name the original failed attempt")
    # Work is owned by PM/CC at the clean checkpoint. Review predecessors
    # must have an actual successful call in this same delivery.
    nodes = {n["node_id"]: n for n in binding["dag"]["nodes"]}
    for required in binding["task"]["requires"]:
        if nodes[required]["node_class"] == "verification":
            results = [a for a in attempts if a["node_id"] == required]
            if (not results or results[-1]["status"] != "PASS"
                    or results[-1].get("source_generation") != generation):
                raise PermissionError("REVIEW_PREDECESSOR_NOT_PASS: " + required)
    attempt = {"node_id": node, "number": len(prior) + 1,
               "source_generation": generation,
               "instruction_digest": digest(instruction), "status": "RUNNING"}
    attempt["id"] = digest([frozen, attempt, len(attempts)])
    attempts.append(attempt)
    return state, attempt


def command(binary: str, root: Path, output: Path, role: dict) -> list[str]:
    scratch = output / "scratch"
    settings = {
        "model_reasoning_effort": role["model_reasoning_effort"],
        "developer_instructions": role["developer_instructions"],
        "features.multi_agent": False, "features.multi_agent_v2": False,
        "agents.enabled": False, "features.plugins": False, "features.apps": False,
        "skills.include_instructions": False, "memories.generate_memories": False,
        "memories.use_memories": False, "approval_policy": "never",
        "default_permissions": "tradebot-review",
        "permissions.tradebot-review.extends": ":read-only",
        "permissions.tradebot-review.network.enabled": False,
        "shell_environment_policy.set.TMPDIR": str(scratch),
        "shell_environment_policy.set.PYTHONDONTWRITEBYTECODE": "1",
        "shell_environment_policy.set." + CHILD_MARKER: "1",
    }
    argv = [binary, "exec", "--ephemeral", "--ignore-user-config", "--strict-config",
            "--cd", str(root), "--model", role["model"]]
    for key, value in settings.items():
        argv += ["-c", key + "=" + json.dumps(value, ensure_ascii=False)]
    argv += ["-c", "permissions.tradebot-review.filesystem={"
             + json.dumps(str(scratch)) + '="write"}',
             "--json", "--color", "never", "--output-last-message", str(output / "verdict.txt"), "-"]
    return argv


def stop_group(process: subprocess.Popen) -> str | None:
    # CLI tools may start a fresh session. Freeze the leader before finding its
    # descendants, so killing only the original process group cannot strand them.
    cleanup_error = None
    try:
        os.killpg(process.pid, signal.SIGSTOP)
    except ProcessLookupError:
        pass
    try:
        rows = subprocess.check_output(["ps", "-axo", "pid=,ppid="], text=True,
                                       timeout=2).splitlines()
        parents = {int(pid): int(parent) for pid, parent in (row.split() for row in rows)}
        owned = {process.pid}
        while True:
            children = {pid for pid, parent in parents.items() if parent in owned} - owned
            if not children:
                break
            owned.update(children)
        for pid in owned - {process.pid}:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    except (OSError, subprocess.SubprocessError) as exc:
        cleanup_error = "DESCENDANT_CLEANUP_UNVERIFIED: " + str(exc)
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)
    return cleanup_error


def execute(argv: list[str], prompt: str, output: Path, root: Path, deadline: float) -> dict:
    env = dict(os.environ, TMPDIR=str(output / "scratch"), PYTHONDONTWRITEBYTECODE="1")
    env[CHILD_MARKER] = "1"
    started = time.monotonic()
    reason = None
    cleanup_error = None
    # A file avoids blocking on a child that never drains a large stdin pipe.
    (output / "input.txt").write_text(prompt)
    with (output / "input.txt").open() as input_file, (output / "events.jsonl").open("w") as log, (output / "stderr.log").open("w") as err:
        process = subprocess.Popen(argv, cwd=root, stdin=input_file, stdout=log,
                                   stderr=err, text=True, env=env, start_new_session=True)
        try:
            with (output / "stderr.log").open("rb") as scan:
                tail = b""
                while process.poll() is None:
                    if time.monotonic() - started >= deadline:
                        reason = "DEADLINE"
                    else:
                        chunk = tail + scan.read(16384)
                        if b"stream disconnected - retrying sampling request" in chunk:
                            reason = "TRANSPORT_FAILURE_NO_RETRY"
                        tail = chunk[-64:]
                    if reason:
                        cleanup_error = stop_group(process)
                        break
                    time.sleep(0.1)
        except BaseException:
            stop_group(process)
            raise
    return {"exit_code": process.returncode, "stop_reason": reason, "cleanup_error": cleanup_error,
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def run(*, root: Path, context: dict, node_id: str, instruction: str,
        output: Path, binary: str, deadline: int = 180, recheck_of: str | None = None) -> dict:
    root = root.resolve(strict=True)
    binding = bind(root, context, node_id)
    policy = binding["policy"]
    if type(deadline) is not int or not 1 <= deadline <= min(300, policy["max_call_duration_ms"] // 1000):
        raise ValueError("deadline must be 1..300 seconds and within the Context budget")
    controller = os.environ.get("CODEX_THREAD_ID")
    if not controller:
        raise PermissionError("CODEX_THREAD_ID controller identity is required")
    executable = Path(shutil.which(binary) or binary).resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("Codex executable is unavailable")
    output = output.resolve()
    common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    if output.is_relative_to(root) or root.is_relative_to(output) or output.is_relative_to(common):
        raise ValueError("output must be outside the source checkout and Git metadata")
    response_identity = {"task_contract_digest": context["task_contract_digest"],
                         "context_artifact_digest": context["artifact_digest"],
                         "context_digest": context["artifact_digest"],
                         "source_head": binding["baseline"]["source_head"],
                         **{key: binding["task"][key] for key in ("role", "native_agent", "node_id")}}
    prompt = (context["shared_task_context_canonical"] + "\n\n"
              + context["role_context_delta_canonical"]
              + "\n\nController binding: " + json.dumps(binding["task"])
              + "\nExactly one assigned result. No child delegation, self-admission, edits, git writes, "
              "external contact or new tasks. Verification commands only via the existing Context-bound "
              "capture-command. PM owns integration. Return one JSON object with verdict "
              "PASS/FAIL/UNVERIFIED, summary, findings and evidence; preserve uncertainty.\n"
              + "Any task/Context/source/role identifiers in your response must match this call, "
              "not a prior review quoted as evidence: " + json.dumps(response_identity) + "\n"
              + instruction)
    if not instruction.strip() or len(prompt.encode()) > policy["max_prompt_utf8_bytes_per_call"]:
        raise ValueError("missing instruction or prompt exceeds the frozen Context budget")
    with delivery_lock(root, binding) as state_path:
        state = json.loads(state_path.read_text()) if state_path.exists() else None
        state, attempt = reserve(state, binding, controller, root, instruction, recheck_of)
        output.mkdir(parents=True, exist_ok=False)
        (output / "scratch").mkdir()
        write_json(state_path, state)  # Spend the attempt before any model process starts.
        write_json(output / "context.json", context)
        (output / "prompt.txt").write_text(prompt)
        argv = command(str(executable), root, output, binding["role"])
        write_json(output / "argv.json", argv)
        result = {"status": "UNVERIFIED", "attempt_id": attempt["id"],
                  "node": binding["task"], "path_scope": binding["paths"],
                  "source_head": binding["baseline"]["source_head"],
                  "context_digest": context["artifact_digest"], "deadline_seconds": deadline,
                  "history": "none", "automatic_retries": 0}
        try:
            remaining = policy["max_wall_clock_ms"] / 1000 - (time.time() - state["started_at"])
            result.update(execute(argv, prompt, output, root, min(deadline, max(0, remaining))))
            if capture_repository_baseline(root) != binding["baseline"]:
                result["error"] = "SOURCE_CHANGED_DURING_REVIEW"
            elif result["exit_code"] == 0 and result["stop_reason"] is None:
                verdict = json.loads((output / "verdict.txt").read_text())
                if not isinstance(verdict, dict) or verdict.get("verdict") not in {"PASS", "FAIL", "UNVERIFIED"}:
                    raise ValueError("missing explicit reviewer verdict")
                # The controller binds bare verdicts to this exact call. Explicit
                # reviewer identifiers must not contradict that trusted binding.
                for label, metadata in (("review", verdict), ("evidence", verdict.get("evidence")),
                                        ("binding", verdict.get("binding"))):
                    if isinstance(metadata, dict):
                        for key, expected in response_identity.items():
                            if key in metadata and metadata[key] != expected:
                                raise ValueError("REVIEW_BINDING_MISMATCH: " + label + "." + key)
                result["review"] = verdict
                result["status"] = verdict["verdict"]
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            result["error"] = str(exc)
        finally:
            attempt["status"] = result["status"]
            attempt["output"] = str(output)
            write_json(output / "result.json", result)
            write_json(state_path, state)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--instruction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--codex", default=shutil.which("codex"))
    parser.add_argument("--deadline", type=int, default=180)
    parser.add_argument("--recheck-of")
    args = parser.parse_args()
    try:
        if not args.codex:
            raise ValueError("Codex CLI is unavailable; pass the installed --codex path")
        result = run(root=args.root, context=json.loads(args.context.read_text()), node_id=args.node,
                     instruction=args.instruction.read_text(), output=args.output, binary=args.codex,
                     deadline=args.deadline, recheck_of=args.recheck_of)
    except (OSError, ValueError, KeyError, TypeError, PermissionError) as exc:
        print(json.dumps({"status": "DENIED", "error": str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
