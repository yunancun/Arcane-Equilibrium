"""Trusted local replay for governance command captures.

Replay is deliberately separate from record-shape validation: callers first
prove that a command capture is canonical and authorized, then use this module
to reproduce its result against the exact current repository generation.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol


class RepositoryCapture(Protocol):
    """Shape required from the canonical repository-capture producer."""

    def __call__(self, scope: Any, *, root: Path) -> dict[str, Any]: ...


RepositoryGenerationDigest = Callable[[dict[str, Any]], str]
RepositoryResolver = Callable[[Path], Path]

EXACT_OUTPUT = "EXACT_OUTPUT"
CANONICAL_TEST_OUTPUT_V1 = "CANONICAL_TEST_OUTPUT_V1"
RESULT_ONLY = "RESULT_ONLY"
REPLAY_CONTRACTS = {EXACT_OUTPUT, CANONICAL_TEST_OUTPUT_V1, RESULT_ONLY}
_DURATION_RE = re.compile(
    rb"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?(?:ms|s)(?![A-Za-z0-9_.])"
)


def command_argv(command: Any) -> tuple[list[str], str]:
    """Parse one command without accepting controls or implicit shell execution."""

    if isinstance(command, str):
        if not command.strip() or command != command.strip():
            raise ValueError("command string must be non-empty and canonical")
        if any(ord(character) < 32 or ord(character) == 127 for character in command):
            raise ValueError("command contains forbidden control characters")
        try:
            argv = shlex.split(command, posix=True)
        except ValueError as error:
            raise ValueError(f"command cannot be parsed conservatively: {error}") from error
    elif isinstance(command, (list, tuple)):
        argv = list(command)
    else:
        raise ValueError("command must be an argv list or a conservatively parsed string")
    if not argv or any(
        not isinstance(argument, str)
        or not argument
        or any(ord(character) < 32 or ord(character) == 127 for character in argument)
        for argument in argv
    ):
        raise ValueError("command argv must contain non-empty strings without controls")
    return argv, shlex.join(argv)


def _is_test_command(argv: list[str]) -> bool:
    return bool(
        argv
        and (
            argv[0].lower() == "pytest"
            or argv[:3] in (["python", "-m", "pytest"], ["python3", "-m", "pytest"])
            or argv[:2] in (
                ["cargo", "test"],
                ["cargo", "check"],
                ["cargo", "clippy"],
                ["node", "--check"],
                ["bash", "-n"],
            )
            or argv[:3] == ["cargo", "fmt", "--check"]
        )
    )


def replay_contract_for(argv: list[str], policy_class: Any) -> str:
    """Select the strongest reproducible contract for one authorized command."""

    if policy_class == "governance_readonly":
        return RESULT_ONLY
    if policy_class == "local_test_adapter" or _is_test_command(argv):
        return CANONICAL_TEST_OUTPUT_V1
    return EXACT_OUTPUT


def recorded_output(replay_contract: str, data: bytes) -> bytes:
    """A result-only check deliberately carries no semantic output channel."""

    return b"" if replay_contract == RESULT_ONLY else data


def _comparable_output(replay_contract: str, data: bytes) -> bytes:
    if replay_contract == CANONICAL_TEST_OUTPUT_V1:
        return _DURATION_RE.sub(b"<duration>", data)
    return data


def validate_trusted_command_replay(
    *,
    argv: list[str],
    recorded_result: Any,
    recorded_exit_code: Any,
    recorded_timed_out: Any,
    recorded_stdout: bytes,
    recorded_stderr: bytes,
    replay_contract: Any,
    recorded_repository_after: dict[str, Any],
    root: Path,
    timeout_seconds: int,
    resolve_repository: RepositoryResolver,
    capture_repository: RepositoryCapture,
    generation_digest: RepositoryGenerationDigest,
) -> list[str]:
    """Reproduce one validated command without permitting generation drift."""

    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or not 1 <= timeout_seconds <= 1800
    ):
        return ["command capture replay timeout is invalid"]

    repository = resolve_repository(root)
    scope = recorded_repository_after.get("scope")
    try:
        current_before = capture_repository(scope, root=repository)
    except (TypeError, ValueError) as error:
        return [f"command capture cannot recheck current generation: {error}"]
    if generation_digest(current_before) != generation_digest(recorded_repository_after):
        return ["command capture is stale relative to the current repository generation"]

    if replay_contract not in REPLAY_CONTRACTS:
        return ["command capture replay contract is invalid"]
    if replay_contract == RESULT_ONLY and (recorded_stdout or recorded_stderr):
        return ["result-only command capture cannot carry semantic output bytes"]

    try:
        replay = subprocess.run(
            argv,
            cwd=repository,
            shell=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        replay_exit_code = replay.returncode
        replay_timed_out = False
        replay_stdout = replay.stdout
        replay_stderr = replay.stderr
        replay_result = "PASS" if replay.returncode == 0 else "FAIL"
    except subprocess.TimeoutExpired as error:
        replay_exit_code = -1
        replay_timed_out = True
        replay_stdout = error.stdout if isinstance(error.stdout, bytes) else b""
        replay_stderr = error.stderr if isinstance(error.stderr, bytes) else b""
        replay_result = "TIMED_OUT"
    except OSError as error:
        replay_exit_code = 127
        replay_timed_out = False
        replay_stdout = b""
        replay_stderr = str(error).encode("utf-8", errors="replace")
        replay_result = "FAIL"

    errors: list[str] = []
    current_after = capture_repository(scope, root=repository)
    if generation_digest(current_before) != generation_digest(current_after):
        errors.append("command capture replay mutated the task-scoped repository generation")
    if (
        replay_result != recorded_result
        or replay_exit_code != recorded_exit_code
        or replay_timed_out is not recorded_timed_out
    ):
        errors.append(
            "command capture claimed result does not reproduce under trusted local replay"
        )
    if replay_contract != RESULT_ONLY and (
        _comparable_output(replay_contract, replay_stdout)
        != _comparable_output(replay_contract, recorded_stdout)
        or _comparable_output(replay_contract, replay_stderr)
        != _comparable_output(replay_contract, recorded_stderr)
    ):
        errors.append(
            "command capture output does not reproduce under its trusted replay contract"
        )
    return errors
