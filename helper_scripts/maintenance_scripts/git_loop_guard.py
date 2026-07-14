#!/usr/bin/env python3
"""Read-only Git guard for loop checkpoints, publication, and main sync.

The guard never stages, commits, fetches, pushes, merges, resets, cleans, removes
worktrees, or mutates a remote. It converts repository state into a fail-closed
``git_loop_guard_v1`` packet so a long-running loop cannot silently carry dirty
work into another iteration or publish from the wrong branch/head.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "git_loop_guard_v1"
PHASES = {
    "start",
    "checkpoint",
    "publish",
    "post-push",
    "main-sync",
    "main-post-sync",
}
DEFAULT_MAX_DIRTY_FILES = 12
DEFAULT_MAX_DIFF_LINES = 1500
DEFAULT_MAX_UNTRACKED_BYTES = 2_000_000


def _git(repo: Path, *args: str, timeout: int = 20) -> subprocess.CompletedProcess[bytes]:
    command = ["git", "-C", str(repo), *args]
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=b"",
            stderr=str(exc).encode("utf-8", errors="replace"),
        )


def _text(repo: Path, *args: str) -> str | None:
    proc = _git(repo, *args)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _nul_paths(repo: Path, *args: str) -> list[str] | None:
    proc = _git(repo, *args)
    if proc.returncode != 0:
        return None
    return [os.fsdecode(item) for item in proc.stdout.split(b"\0") if item]


def _true_remote_head(repo: Path, ref: str) -> str | None:
    proc = _git(repo, "ls-remote", "origin", ref)
    if proc.returncode != 0:
        return None
    fields = proc.stdout.decode("utf-8", errors="replace").split()
    return fields[0] if fields else None


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool | None:
    proc = _git(repo, "merge-base", "--is-ancestor", ancestor, descendant)
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


def _diff_lines(repo: Path) -> tuple[int, bool]:
    proc = _git(repo, "diff", "--numstat", "HEAD")
    if proc.returncode != 0:
        return 0, True
    total = 0
    binary = False
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        fields = line.split("\t", 2)
        if len(fields) < 2:
            continue
        if fields[0] == "-" or fields[1] == "-":
            binary = True
            continue
        try:
            total += int(fields[0]) + int(fields[1])
        except ValueError:
            binary = True
    return total, binary


def _untracked_bytes(repo: Path, paths: Iterable[str]) -> tuple[int, bool]:
    total = 0
    unreadable = False
    for path in paths:
        try:
            candidate = (repo / path).resolve()
            candidate.relative_to(repo.resolve())
            if candidate.is_file():
                total += candidate.stat().st_size
            else:
                unreadable = True
        except (OSError, ValueError):
            unreadable = True
    return total, unreadable


def _allowed(path: str, allow_paths: Iterable[str]) -> bool:
    for item in allow_paths:
        normalized = item.strip().removeprefix("./")
        if not normalized:
            continue
        if normalized.endswith("/") and path.startswith(normalized):
            return True
        if path == normalized:
            return True
    return False


def inspect_repository(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    branch = _text(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = _text(repo, "rev-parse", "HEAD")
    upstream = _text(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    tracked = _nul_paths(repo, "diff", "--name-only", "-z", "HEAD", "--")
    staged = _nul_paths(repo, "diff", "--cached", "--name-only", "-z", "--")
    untracked = _nul_paths(
        repo, "ls-files", "--others", "--exclude-standard", "-z", "--"
    )
    diff_lines, binary_diff = _diff_lines(repo)
    untracked_bytes, unreadable_untracked = _untracked_bytes(repo, untracked or [])
    dirty_paths = sorted(set((tracked or []) + (untracked or [])))
    return {
        "repo_root": str(repo),
        "branch": branch,
        "head": head,
        "upstream": upstream,
        "dirty_paths": dirty_paths,
        "dirty_file_count": len(dirty_paths),
        "staged_paths": sorted(staged or []),
        "tracked_diff_lines": diff_lines,
        "binary_diff_present": binary_diff,
        "untracked_bytes": untracked_bytes,
        "untracked_unreadable": unreadable_untracked,
        "local_origin_main": _text(repo, "rev-parse", "origin/main"),
        "true_origin_main": _true_remote_head(repo, "refs/heads/main"),
    }


def evaluate(
    repo: Path,
    *,
    phase: str,
    expected_branch: str | None = None,
    expected_head: str | None = None,
    expected_origin_head: str | None = None,
    allow_paths: Iterable[str] = (),
    max_dirty_files: int = DEFAULT_MAX_DIRTY_FILES,
    max_diff_lines: int = DEFAULT_MAX_DIFF_LINES,
    max_untracked_bytes: int = DEFAULT_MAX_UNTRACKED_BYTES,
) -> dict[str, Any]:
    if phase not in PHASES:
        raise ValueError(f"unsupported phase: {phase}")
    state = inspect_repository(repo)
    reasons: list[str] = []
    branch = state["branch"]
    head = state["head"]
    dirty = state["dirty_paths"]
    true_main = state["true_origin_main"]
    local_main = state["local_origin_main"]

    if branch is None:
        reasons.append("DETACHED_HEAD")
    if head is None:
        reasons.append("HEAD_UNAVAILABLE")

    feature_phase = phase in {"start", "checkpoint", "publish", "post-push"}
    if feature_phase:
        if not expected_branch:
            reasons.append("EXPECTED_BRANCH_REQUIRED")
        elif branch != expected_branch:
            reasons.append("BRANCH_MISMATCH")
        if branch == "main":
            reasons.append("DIRECT_MAIN_LOOP_FORBIDDEN")
        if not expected_head:
            reasons.append("EXPECTED_HEAD_REQUIRED")
        elif head != expected_head:
            reasons.append("HEAD_DRIFT")
        expected_upstream = f"origin/{branch}" if branch else None
        if state["upstream"] not in {None, expected_upstream}:
            reasons.append("UPSTREAM_MISMATCH")

    if phase in {"start", "publish", "post-push", "main-sync", "main-post-sync"} and dirty:
        reasons.append("DIRTY_WORKTREE")

    if phase == "checkpoint":
        allow = tuple(allow_paths)
        if not allow:
            reasons.append("ALLOWLIST_REQUIRED")
        unowned = [path for path in dirty if not _allowed(path, allow)]
        if unowned:
            reasons.append("UNOWNED_DIRTY_PATH")
        if state["staged_paths"]:
            reasons.append("PREEXISTING_STAGED_CHANGES")
        if state["dirty_file_count"] > max_dirty_files:
            reasons.append("DIRTY_FILE_BUDGET_EXCEEDED")
        if state["tracked_diff_lines"] > max_diff_lines:
            reasons.append("DIFF_LINE_BUDGET_EXCEEDED")
        if state["binary_diff_present"]:
            reasons.append("BINARY_DIFF_REQUIRES_EXPLICIT_CHECKPOINT")
        if state["untracked_unreadable"]:
            reasons.append("UNTRACKED_PATH_UNREADABLE")
        if state["untracked_bytes"] > max_untracked_bytes:
            reasons.append("UNTRACKED_BYTE_BUDGET_EXCEEDED")

    if phase in {"publish", "post-push", "main-sync", "main-post-sync"}:
        if true_main is None:
            reasons.append("TRUE_ORIGIN_MAIN_UNAVAILABLE")
        if local_main != true_main:
            reasons.append("REMOTE_TRACKING_STALE")

    if phase in {"publish", "post-push"}:
        if true_main and head:
            ancestor = _is_ancestor(repo.resolve(), true_main, head)
            if ancestor is not True:
                reasons.append(
                    "ORIGIN_MAIN_NOT_ANCESTOR"
                    if ancestor is False
                    else "ORIGIN_MAIN_TOPOLOGY_UNAVAILABLE"
                )
        if phase == "post-push" and branch and head:
            remote_branch = _true_remote_head(repo.resolve(), f"refs/heads/{branch}")
            state["true_remote_branch_head"] = remote_branch
            if remote_branch != head:
                reasons.append("REMOTE_BRANCH_HEAD_MISMATCH")

    if phase in {"main-sync", "main-post-sync"}:
        if branch != "main":
            reasons.append("MAIN_WORKTREE_REQUIRED")
        if not expected_origin_head:
            reasons.append("EXPECTED_ORIGIN_HEAD_REQUIRED")
        elif true_main != expected_origin_head:
            reasons.append("ORIGIN_HEAD_DRIFT")
        if phase == "main-sync" and head and true_main:
            ancestor = _is_ancestor(repo.resolve(), head, true_main)
            if ancestor is not True:
                reasons.append(
                    "LOCAL_MAIN_DIVERGED"
                    if ancestor is False
                    else "LOCAL_MAIN_TOPOLOGY_UNAVAILABLE"
                )
        if phase == "main-post-sync" and head != true_main:
            reasons.append("LOCAL_MAIN_NOT_SYNCED")

    return {
        "schema_version": SCHEMA_VERSION,
        "phase": phase,
        "status": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "state": state,
        "limits": {
            "max_dirty_files": max_dirty_files,
            "max_diff_lines": max_diff_lines,
            "max_untracked_bytes": max_untracked_bytes,
        },
        "mutated_local": False,
        "mutated_remote": False,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--phase", choices=sorted(PHASES), required=True)
    parser.add_argument("--expected-branch")
    parser.add_argument("--expected-head")
    parser.add_argument("--expected-origin-head")
    parser.add_argument("--allow-path", action="append", default=[])
    parser.add_argument("--max-dirty-files", type=int, default=DEFAULT_MAX_DIRTY_FILES)
    parser.add_argument("--max-diff-lines", type=int, default=DEFAULT_MAX_DIFF_LINES)
    parser.add_argument(
        "--max-untracked-bytes", type=int, default=DEFAULT_MAX_UNTRACKED_BYTES
    )
    parser.add_argument("--human", action="store_true")
    return parser.parse_args(argv)


def _human(packet: dict[str, Any]) -> str:
    state = packet["state"]
    return "\n".join(
        [
            f"status: {packet['status']}",
            f"phase: {packet['phase']}",
            f"branch: {state['branch']}",
            f"head: {state['head']}",
            f"upstream: {state['upstream']}",
            f"dirty_file_count: {state['dirty_file_count']}",
            f"dirty_paths: {state['dirty_paths']}",
            f"reasons: {packet['reasons']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = evaluate(
        args.repo,
        phase=args.phase,
        expected_branch=args.expected_branch,
        expected_head=args.expected_head,
        expected_origin_head=args.expected_origin_head,
        allow_paths=args.allow_path,
        max_dirty_files=args.max_dirty_files,
        max_diff_lines=args.max_diff_lines,
        max_untracked_bytes=args.max_untracked_bytes,
    )
    print(_human(packet) if args.human else json.dumps(packet, indent=2, sort_keys=True))
    return 0 if packet["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
