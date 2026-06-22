#!/usr/bin/env python3
"""Operator-gated runtime source reconcile apply helper.

用途：
- 將 remote read-only reconcile probe 的結果轉成可審核的 apply packet。
- 默認 dry-run，只輸出將要執行的 fetch/archive/reset/clean/verify commands。
- 真正 apply 必須同時滿足 ``--apply``、expected SHA/HEAD、review acceptance、
  target-wins confirmation，以及 ``OPENCLAW_RUNTIME_SOURCE_RECONCILE_APPLY=1``。

邊界：
- dry-run 不改 local/remote。
- apply 僅限 git source checkout reconcile；不改 crontab/env/DB/Bybit/order/risk/strategy，
  不 deploy/rebuild/restart。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_source_remote_reconcile_probe as remote_probe  # noqa: E402


SCHEMA_VERSION = "runtime_source_reconcile_apply_plan_v1"
APPLY_ENV = "OPENCLAW_RUNTIME_SOURCE_RECONCILE_APPLY"
DRY_RUN_BOUNDARY = (
    "dry-run apply packet only; no remote fetch/pull/checkout/reset/clean/stash, "
    "no crontab/env/DB/Bybit/order/risk/strategy mutation"
)
APPLY_BOUNDARY = (
    "operator-gated source checkout reconcile only; may run git fetch/reset/clean "
    "and write a source archive under the chosen archive dir; no crontab/env/DB/"
    "Bybit/order/risk/strategy mutation, no deploy/rebuild/restart"
)


class ShellClient(Protocol):
    def run_shell(self, command: str) -> subprocess.CompletedProcess[bytes]:
        ...


class LocalShellClient:
    """測試/開發用：在本地 shell 執行 apply command。"""

    def __init__(self, *, timeout: int = 30) -> None:
        self.timeout = timeout

    def run_shell(self, command: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            command,
            shell=True,
            check=False,
            capture_output=True,
            timeout=self.timeout,
        )


class SshShellClient:
    """SSH apply client。只在 env gate + explicit apply 後使用。"""

    def __init__(self, ssh_host: str, *, timeout: int = 60) -> None:
        self.ssh_host = ssh_host
        self.timeout = timeout

    def run_shell(self, command: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["ssh", self.ssh_host, command],
            check=False,
            capture_output=True,
            timeout=self.timeout,
        )


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _safe_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _q(value: str | Path) -> str:
    return shlex.quote(str(value))


def _class_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    classes = plan.get("classes") or {}
    if not isinstance(classes, dict):
        return rows
    for value in classes.values():
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
    return rows


def _dirty_paths(plan: dict[str, Any]) -> list[str]:
    paths = []
    for row in _class_rows(plan):
        path = row.get("path")
        if isinstance(path, str) and path:
            paths.append(path)
    return sorted(dict.fromkeys(paths))


def _existing_worktree_paths(plan: dict[str, Any]) -> list[str]:
    paths = []
    for row in _class_rows(plan):
        path = row.get("path")
        if not isinstance(path, str) or not path:
            continue
        kind = row.get("remote_worktree_kind")
        if kind == "ok":
            paths.append(path)
    return sorted(dict.fromkeys(paths))


def _untracked_paths(plan: dict[str, Any]) -> list[str]:
    paths = []
    for row in _class_rows(plan):
        path = row.get("path")
        if isinstance(path, str) and path and row.get("category") == "untracked":
            paths.append(path)
    return sorted(dict.fromkeys(paths))


def _path_args(paths: list[str]) -> str:
    return " ".join(_q(path) for path in paths)


def _review_packet_status(review_packet: Path | None) -> dict[str, Any]:
    if review_packet is None:
        return {"provided": False, "exists": False}
    return {
        "provided": True,
        "path": str(review_packet),
        "exists": review_packet.exists(),
    }


def _build_commands(
    plan: dict[str, Any],
    *,
    archive_dir: str,
    fetch_ref: str,
) -> tuple[list[dict[str, Any]], str]:
    remote_repo_root = str(plan.get("remote_repo_root") or "")
    target_commit = str(plan.get("target_commit") or "")
    short = target_commit[:12] or "unknown"
    archive_path = f"{archive_dir.rstrip('/')}/source_reconcile_{_safe_stamp()}_{short}"
    git = f"git -C {_q(remote_repo_root)}"
    archive_q = _q(archive_path)
    existing_paths = _existing_worktree_paths(plan)
    untracked_paths = _untracked_paths(plan)

    commands: list[dict[str, Any]] = [
        {
            "step": "fetch_target_ref",
            "command": f"{git} fetch origin {_q(fetch_ref)}",
            "mutates_remote": True,
            "reason": "make target object available on runtime before reset",
        },
        {
            "step": "verify_target_object",
            "command": f"{git} rev-parse --verify {_q(target_commit + '^{commit}')}",
            "mutates_remote": False,
            "reason": "fail closed if fetch did not make the approved target available",
        },
        {
            "step": "create_archive_dir",
            "command": f"mkdir -p {archive_q}",
            "mutates_remote": True,
            "reason": "create source reconcile archive directory before destructive git commands",
        },
        {
            "step": "archive_status",
            "command": (
                f"{git} status --porcelain=v1 --untracked-files=all "
                f"> {archive_q}/status.porcelain"
            ),
            "mutates_remote": True,
            "reason": "preserve pre-reconcile dirty status manifest",
        },
        {
            "step": "archive_tracked_diff",
            "command": f"{git} diff --binary > {archive_q}/tracked.diff",
            "mutates_remote": True,
            "reason": "preserve tracked worktree diff before reset",
        },
        {
            "step": "reset_to_target",
            "command": f"{git} reset --hard {_q(target_commit)}",
            "mutates_remote": True,
            "reason": "operator-approved target-wins source reconcile",
        },
        {
            "step": "verify_head",
            "command": f"{git} rev-parse HEAD",
            "mutates_remote": False,
            "reason": "operator should confirm stdout equals approved target commit",
        },
        {
            "step": "verify_status",
            "command": f"{git} status --porcelain=v1 --untracked-files=all",
            "mutates_remote": False,
            "reason": "operator should confirm no remaining dirty/untracked source paths",
        },
    ]
    if existing_paths:
        commands.insert(
            5,
            {
                "step": "archive_existing_worktree_paths",
                "command": (
                    f"tar -czf {archive_q}/worktree_paths.tgz -C {_q(remote_repo_root)} "
                    f"-- {_path_args(existing_paths)}"
                ),
                "mutates_remote": True,
                "reason": "preserve existing dirty/untracked file bytes before reset/clean",
                "path_count": len(existing_paths),
            },
        )
    if untracked_paths:
        commands.insert(
            -2,
            {
                "step": "clean_untracked_paths",
                "command": f"{git} clean -fd -- {_path_args(untracked_paths)}",
                "mutates_remote": True,
                "reason": "remove untracked files recorded by the reviewed remote probe",
                "path_count": len(untracked_paths),
            },
        )
    return commands, archive_path


def build_apply_plan(
    local_repo_root: Path,
    *,
    target_ref: str,
    remote_repo_root: str,
    remote_label: str,
    probe_client: remote_probe.RemoteClient,
    apply_requested: bool,
    apply_env_value: str | None,
    expected_target_commit: str | None,
    expected_remote_head: str | None,
    expected_dirty_count: int | None,
    expected_review_required_count: int | None,
    review_accepted: bool,
    confirm_target_wins: bool,
    review_packet: Path | None,
    archive_dir: str,
    fetch_ref: str,
) -> dict[str, Any]:
    probe_plan = remote_probe.build_remote_plan(
        local_repo_root,
        target_ref=target_ref,
        remote_repo_root=remote_repo_root,
        remote_label=remote_label,
        client=probe_client,
        max_paths_per_class=10_000,
        include_digests=False,
    )
    commands, archive_path = _build_commands(
        probe_plan,
        archive_dir=archive_dir,
        fetch_ref=fetch_ref,
    )
    review_required_count = int(probe_plan.get("review_required_path_count") or 0)
    dirty_count = int(probe_plan.get("dirty_path_count") or 0)
    target_commit = probe_plan.get("target_commit")
    remote_head = probe_plan.get("remote_head")
    review_packet_status = _review_packet_status(review_packet)

    blockers: list[str] = []
    warnings: list[str] = []

    if probe_plan.get("target_ref_status") != "AVAILABLE_LOCALLY":
        blockers.append("local_target_ref_unavailable")
    if probe_plan.get("status") in {"REMOTE_GIT_UNAVAILABLE", "REMOTE_STATUS_UNAVAILABLE"}:
        blockers.append("remote_probe_unavailable")
    if expected_target_commit is None:
        if apply_requested:
            blockers.append("expected_target_commit_required_for_apply")
        else:
            warnings.append("expected_target_commit_not_supplied")
    elif target_commit != expected_target_commit:
        blockers.append("expected_target_commit_mismatch")
    if expected_remote_head is None:
        if apply_requested:
            blockers.append("expected_remote_head_required_for_apply")
        else:
            warnings.append("expected_remote_head_not_supplied")
    elif remote_head != expected_remote_head:
        blockers.append("expected_remote_head_mismatch")
    if expected_dirty_count is not None and dirty_count != expected_dirty_count:
        blockers.append("expected_dirty_count_mismatch")
    if (
        expected_review_required_count is not None
        and review_required_count != expected_review_required_count
    ):
        blockers.append("expected_review_required_count_mismatch")
    if review_required_count > 0:
        if not review_accepted:
            blockers.append("review_required_paths_not_operator_accepted")
        if not confirm_target_wins:
            blockers.append("target_wins_not_confirmed_for_review_required_paths")
        if not review_packet_status["provided"]:
            blockers.append("review_packet_required_for_review_required_paths")
        elif not review_packet_status["exists"]:
            blockers.append("review_packet_path_not_found")
    if apply_requested and apply_env_value != "1":
        blockers.append("apply_env_gate_not_set")

    if not apply_requested:
        status = "DRY_RUN_OPERATOR_APPROVAL_REQUIRED"
    elif blockers:
        status = "APPLY_BLOCKED"
    else:
        status = "APPLY_READY"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now_iso(),
        "status": status,
        "apply_requested": apply_requested,
        "apply_env": APPLY_ENV,
        "apply_env_gate_open": apply_env_value == "1",
        "mutated_remote": False,
        "mutated_local": False,
        "boundary": APPLY_BOUNDARY if apply_requested else DRY_RUN_BOUNDARY,
        "target_ref": target_ref,
        "target_commit": target_commit,
        "remote_label": remote_label,
        "remote_repo_root": remote_repo_root,
        "remote_head": remote_head,
        "remote_origin_main": probe_plan.get("remote_origin_main"),
        "remote_target_object_available": probe_plan.get("remote_target_object_available"),
        "probe_status": probe_plan.get("status"),
        "dirty_path_count": dirty_count,
        "review_required_path_count": review_required_count,
        "content_equivalent_path_count": probe_plan.get("content_equivalent_path_count"),
        "class_counts": probe_plan.get("class_counts"),
        "review_required_paths": probe_plan.get("review_required_paths") or [],
        "content_equivalent_paths": probe_plan.get("content_equivalent_paths") or [],
        "review_packet": review_packet_status,
        "review_accepted": review_accepted,
        "confirm_target_wins": confirm_target_wins,
        "archive_path": archive_path,
        "fetch_ref": fetch_ref,
        "blockers": blockers,
        "warnings": warnings,
        "commands": commands,
        "answers": {
            "dry_run_only": not apply_requested,
            "apply_ready": status == "APPLY_READY",
            "requires_operator_authorization": True,
            "will_archive_before_reset": True,
            "will_fetch_target_before_reset": True,
            "will_reset_to_exact_target": status == "APPLY_READY",
            "will_clean_untracked_probe_paths": bool(_untracked_paths(probe_plan)),
            "runtime_cron_or_env_or_db_or_trading_mutation": False,
        },
        "next_actions": (
            ["operator_review_apply_packet_then_rerun_with_apply_env_and_expected_values"]
            if not apply_requested
            else (
                ["fix_apply_blockers_before_runtime_source_reconcile"]
                if blockers
                else [
                    "execute_commands_in_order",
                    "rerun_runtime_source_remote_reconcile_probe_after_apply",
                    "run_direct_runtime_planner_after_target_object_available",
                    "only_then_continue_demo_learning_stack_install_preflight",
                ]
            )
        ),
        "probe_plan": probe_plan,
    }


def execute_apply_plan(
    plan: dict[str, Any],
    *,
    shell_client: ShellClient,
) -> dict[str, Any]:
    if plan.get("status") != "APPLY_READY":
        return {
            **plan,
            "status": "APPLY_NOT_EXECUTED",
            "execution_results": [],
            "execution_error": "plan_not_apply_ready",
        }

    results: list[dict[str, Any]] = []
    for command in plan.get("commands") or []:
        if not isinstance(command, dict):
            continue
        cmd = str(command.get("command") or "")
        proc = shell_client.run_shell(cmd)
        row = {
            "step": command.get("step"),
            "returncode": proc.returncode,
            "stdout": proc.stdout.decode("utf-8", errors="replace")[-4000:],
            "stderr": proc.stderr.decode("utf-8", errors="replace")[-4000:],
        }
        results.append(row)
        if proc.returncode != 0:
            return {
                **plan,
                "status": "APPLY_FAILED",
                "mutated_remote": True,
                "execution_results": results,
                "execution_error": f"command_failed:{command.get('step')}",
            }
    return {
        **plan,
        "status": "APPLY_COMMANDS_COMPLETED_VERIFY_WITH_PLANNER",
        "mutated_remote": True,
        "execution_results": results,
        "next_actions": [
            "rerun_runtime_source_remote_reconcile_probe_after_apply",
            "run_direct_runtime_planner_after_target_object_available",
            "continue_demo_learning_stack_install_preflight_if_source_clean",
        ],
    }


def _render_human(plan: dict[str, Any]) -> str:
    lines = [
        f"status: {plan.get('status')}",
        f"remote_label: {plan.get('remote_label')}",
        f"remote_repo_root: {plan.get('remote_repo_root')}",
        f"target_ref: {plan.get('target_ref')} ({plan.get('target_commit')})",
        f"remote_head: {plan.get('remote_head')}",
        f"probe_status: {plan.get('probe_status')}",
        f"dirty_path_count: {plan.get('dirty_path_count')}",
        f"review_required_path_count: {plan.get('review_required_path_count')}",
        f"archive_path: {plan.get('archive_path')}",
    ]
    blockers = plan.get("blockers") or []
    if blockers:
        lines.append("blockers:")
        for blocker in blockers:
            lines.append(f"  - {blocker}")
    lines.append("commands:")
    for command in plan.get("commands") or []:
        lines.append(f"  - [{command.get('step')}] {command.get('command')}")
    lines.append(f"boundary: {plan.get('boundary')}")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-repo-root", default=".", help="local git repo with target ref")
    parser.add_argument("--target-ref", default="origin/main", help="approved local target ref/sha")
    parser.add_argument("--remote-mode", choices=("ssh", "local"), default="ssh")
    parser.add_argument("--ssh-host", default="trade-core", help="SSH host for remote-mode=ssh")
    parser.add_argument(
        "--remote-repo-root",
        default="/home/ncyu/BybitOpenClaw/srv",
        help="remote runtime repo root",
    )
    parser.add_argument("--fetch-ref", default="main", help="origin ref to fetch before reset")
    parser.add_argument(
        "--archive-dir",
        default="/tmp/openclaw/runtime_source_reconcile_archive",
        help="remote archive dir used only in apply mode",
    )
    parser.add_argument("--expected-target-commit", default=None)
    parser.add_argument("--expected-remote-head", default=None)
    parser.add_argument("--expected-dirty-count", type=int, default=None)
    parser.add_argument("--expected-review-required-count", type=int, default=None)
    parser.add_argument("--review-packet", type=Path, default=None)
    parser.add_argument("--review-accepted", action="store_true")
    parser.add_argument("--confirm-target-wins", action="store_true")
    parser.add_argument("--apply", action="store_true", help="execute apply commands when all gates pass")
    parser.add_argument("--json-output", type=Path, default=None, help="optional local JSON output path")
    parser.add_argument("--human", action="store_true", help="print compact summary")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.remote_mode == "local":
        probe_client: remote_probe.RemoteClient = remote_probe.LocalWorktreeClient(
            Path(args.remote_repo_root)
        )
        shell_client: ShellClient = LocalShellClient()
        remote_label = f"local:{args.remote_repo_root}"
    else:
        probe_client = remote_probe.SshWorktreeClient(args.ssh_host, args.remote_repo_root)
        shell_client = SshShellClient(args.ssh_host)
        remote_label = f"ssh:{args.ssh_host}"

    plan = build_apply_plan(
        Path(args.local_repo_root),
        target_ref=args.target_ref,
        remote_repo_root=args.remote_repo_root,
        remote_label=remote_label,
        probe_client=probe_client,
        apply_requested=args.apply,
        apply_env_value=os.environ.get(APPLY_ENV),
        expected_target_commit=args.expected_target_commit,
        expected_remote_head=args.expected_remote_head,
        expected_dirty_count=args.expected_dirty_count,
        expected_review_required_count=args.expected_review_required_count,
        review_accepted=args.review_accepted,
        confirm_target_wins=args.confirm_target_wins,
        review_packet=args.review_packet,
        archive_dir=args.archive_dir,
        fetch_ref=args.fetch_ref,
    )

    if args.apply and plan.get("status") == "APPLY_READY":
        plan = execute_apply_plan(plan, shell_client=shell_client)

    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.human:
        print(_render_human(plan))
    else:
        print(json.dumps(plan, indent=2, sort_keys=True))

    if args.apply and plan.get("status") != "APPLY_COMMANDS_COMPLETED_VERIFY_WITH_PLANNER":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
