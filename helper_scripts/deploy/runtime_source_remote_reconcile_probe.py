#!/usr/bin/env python3
"""Mac 端 runtime source reconcile 只讀探針。

用途：
- local repo 已有 approved target commit，但 runtime checkout 尚未 fetch/sync
  該 object 時，仍可用 local target tree 與 remote worktree 做逐檔比對。
- 透過 SSH 只讀取 remote git status、HEAD、worktree file/symlink bytes。

邊界：
- remote 端不 fetch、不 pull、不 checkout、不 reset、不 clean、不 stash。
- 不改 crontab/env/DB/Bybit/order/risk/strategy。
- 只有顯式 ``--json-output`` 會在本地寫出 plan artifact。
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_source_reconcile_planner as local_planner  # noqa: E402


SCHEMA_VERSION = "runtime_source_remote_reconcile_plan_v1"
BOUNDARY = (
    "read-only local target-tree plus remote git/worktree SSH probe with optional "
    "local JSON artifact write; no remote fetch/pull/checkout/reset/clean/stash, "
    "no crontab/env/DB/Bybit/order/risk/strategy mutation"
)


class RemoteClient(Protocol):
    def git_bytes(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        ...

    def git_text(self, args: list[str], *, check: bool = True) -> str | None:
        ...

    def read_path(self, rel_path: str) -> dict[str, Any]:
        ...


class LocalWorktreeClient:
    """測試/開發用：用本地 repo 模擬 remote worktree。"""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def git_bytes(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        return local_planner._git(self.repo_root, args, check=check)

    def git_text(self, args: list[str], *, check: bool = True) -> str | None:
        return local_planner._git_text(self.repo_root, args, check=check)

    def read_path(self, rel_path: str) -> dict[str, Any]:
        data, mode, error = local_planner._worktree_bytes(self.repo_root, rel_path)
        if error:
            return {"kind": "unreadable", "error": error, "mode": mode}
        if mode in {"absent", "nonfile"}:
            return {"kind": mode, "mode": mode}
        return {"kind": "ok", "mode": mode, "data": data}


class SshWorktreeClient:
    """SSH 只讀 client。所有 remote command 都是 git/status/path read。"""

    def __init__(self, ssh_host: str, remote_repo_root: str, *, timeout: int = 30) -> None:
        self.ssh_host = ssh_host
        self.remote_repo_root = remote_repo_root
        self.timeout = timeout

    def _run(self, command: str, *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        proc = subprocess.run(
            ["ssh", self.ssh_host, command],
            check=False,
            capture_output=True,
            timeout=self.timeout,
        )
        if check and proc.returncode != 0:
            raise local_planner.GitCommandError(
                ["ssh", self.ssh_host, command],
                proc.returncode,
                proc.stdout,
                proc.stderr,
            )
        return proc

    def git_bytes(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        quoted = " ".join(shlex.quote(arg) for arg in args)
        command = f"git -C {shlex.quote(self.remote_repo_root)} {quoted}"
        return self._run(command, check=check)

    def git_text(self, args: list[str], *, check: bool = True) -> str | None:
        proc = self.git_bytes(args, check=check)
        if proc.returncode != 0:
            return None
        return proc.stdout.decode("utf-8", errors="surrogateescape").strip()

    def read_path(self, rel_path: str) -> dict[str, Any]:
        script = r"""
import base64
import json
import os
import stat
import sys

root, rel = sys.argv[1], sys.argv[2]
path = os.path.join(root, rel)
try:
    st = os.lstat(path)
except FileNotFoundError:
    print(json.dumps({"kind": "absent"}))
    raise SystemExit(0)
except OSError as exc:
    print(json.dumps({"kind": "unreadable", "error": f"{type(exc).__name__}:{exc}"}))
    raise SystemExit(0)

mode = st.st_mode
if stat.S_ISLNK(mode):
    try:
        data = os.readlink(path).encode("utf-8", errors="surrogateescape")
    except OSError as exc:
        print(json.dumps({"kind": "unreadable", "error": f"{type(exc).__name__}:{exc}"}))
        raise SystemExit(0)
    payload = {"kind": "ok", "mode": "120000", "data_b64": base64.b64encode(data).decode("ascii")}
elif stat.S_ISREG(mode):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print(json.dumps({"kind": "unreadable", "error": f"{type(exc).__name__}:{exc}"}))
        raise SystemExit(0)
    git_mode = "100755" if (mode & 0o111) else "100644"
    payload = {"kind": "ok", "mode": git_mode, "data_b64": base64.b64encode(data).decode("ascii")}
else:
    payload = {"kind": "nonfile", "mode": oct(mode)}
print(json.dumps(payload, sort_keys=True))
"""
        command = " ".join(
            [
                "python3",
                "-c",
                shlex.quote(script),
                shlex.quote(self.remote_repo_root),
                shlex.quote(rel_path),
            ]
        )
        proc = self._run(command, check=False)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout).decode("utf-8", errors="replace").strip()
            return {"kind": "unreadable", "error": err or f"ssh_rc:{proc.returncode}"}
        try:
            payload = json.loads(proc.stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            return {"kind": "unreadable", "error": f"bad_remote_json:{exc}"}
        if payload.get("kind") == "ok":
            payload["data"] = base64.b64decode(payload.get("data_b64") or "")
            payload.pop("data_b64", None)
        return payload


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _sha256_or_none(data: bytes | None) -> str | None:
    if data is None:
        return None
    return hashlib.sha256(data).hexdigest()


def _remote_target_available(client: RemoteClient, target_commit: str) -> bool | None:
    proc = client.git_bytes(
        ["rev-parse", "--verify", f"{target_commit}^{{commit}}"],
        check=False,
    )
    if proc.returncode == 0:
        return True
    if proc.returncode == 128:
        return False
    return None


def _remote_git_status(client: RemoteClient) -> tuple[bytes | None, str | None]:
    try:
        proc = client.git_bytes(
            ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
            check=True,
        )
    except (local_planner.GitCommandError, OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    return proc.stdout, None


def _classify_remote_entry(
    local_repo_root: Path,
    target_commit: str,
    client: RemoteClient,
    entry: dict[str, str | None],
    *,
    include_digests: bool,
) -> dict[str, Any]:
    rel_path = entry.get("path") or ""
    status_code = entry.get("status_code") or "UNKNOWN"
    category = "untracked" if status_code == "??" else "tracked_change"
    target = local_planner._target_blob(local_repo_root, target_commit, rel_path)
    target_mode = local_planner._target_mode(local_repo_root, target_commit, rel_path)
    remote = client.read_path(rel_path)
    remote_kind = str(remote.get("kind") or "unreadable")
    remote_mode = remote.get("mode")
    remote_bytes = remote.get("data") if isinstance(remote.get("data"), bytes) else None

    if remote_kind == "unreadable":
        classification = "unreadable_worktree_path"
        reason = str(remote.get("error") or "remote_path_unreadable")
    elif category == "tracked_change":
        if remote_kind == "absent" and target is None:
            classification = "tracked_absent_equals_target_absent"
            reason = "remote_worktree_path_absent_and_target_path_absent"
        elif remote_kind in {"absent", "nonfile"}:
            classification = "tracked_missing_or_nonfile"
            reason = f"remote_worktree_path_{remote_kind}"
        elif target is None:
            classification = "tracked_path_absent_from_target"
            reason = "local_target_tree_has_no_matching_path"
        elif remote_bytes == target:
            classification = "tracked_dirty_equals_target"
            reason = "remote_worktree_content_equals_local_target_ref"
        else:
            classification = "tracked_dirty_differs_from_target"
            reason = "remote_worktree_content_differs_from_local_target_ref"
    else:
        if remote_kind in {"absent", "nonfile"}:
            classification = "unreadable_worktree_path"
            reason = f"remote_untracked_path_{remote_kind}"
        elif target is None:
            classification = "untracked_not_in_target"
            reason = "remote_untracked_path_is_local_only_against_target_ref"
        elif remote_bytes == target:
            classification = "untracked_equals_target"
            reason = "remote_untracked_content_equals_local_target_ref"
        else:
            classification = "untracked_conflicts_with_target_path"
            reason = "remote_untracked_content_differs_from_local_target_ref"

    row: dict[str, Any] = {
        "path": rel_path,
        "old_path": entry.get("old_path"),
        "status_code": status_code,
        "category": category,
        "classification": classification,
        "review_required": classification in local_planner.REVIEW_REQUIRED_CLASSES,
        "reason": reason,
        "target_path_exists": target is not None,
        "target_mode": target_mode,
        "remote_worktree_kind": remote_kind,
        "remote_worktree_mode": remote_mode,
        "mode_matches_target": (
            None
            if target_mode is None or remote_mode in {None, "absent", "nonfile", "unreadable"}
            else target_mode == remote_mode
        ),
    }
    if include_digests:
        row["target_sha256"] = _sha256_or_none(target)
        row["remote_worktree_sha256"] = _sha256_or_none(remote_bytes)
    return row


def _limit_classes(
    classes: dict[str, list[dict[str, Any]]],
    max_paths_per_class: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bool]]:
    limited: dict[str, list[dict[str, Any]]] = {}
    truncated: dict[str, bool] = {}
    for key in local_planner.CLASS_KEYS:
        rows = classes.get(key, [])
        limited[key] = rows[:max_paths_per_class]
        truncated[key] = len(rows) > max_paths_per_class
    return limited, truncated


def build_remote_plan(
    local_repo_root: Path,
    *,
    target_ref: str,
    remote_repo_root: str,
    remote_label: str,
    client: RemoteClient,
    max_paths_per_class: int = 50,
    include_digests: bool = False,
) -> dict[str, Any]:
    local_repo_root = local_repo_root.resolve()
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now_iso(),
        "local_repo_root": str(local_repo_root),
        "target_ref": target_ref,
        "remote_repo_root": remote_repo_root,
        "remote_label": remote_label,
        "boundary": BOUNDARY,
        "mutated_remote": False,
        "mutated_local": False,
    }

    target_proc = local_planner._git(
        local_repo_root,
        ["rev-parse", "--verify", f"{target_ref}^{{commit}}"],
        check=False,
    )
    if target_proc.returncode != 0:
        err = (target_proc.stderr or target_proc.stdout).decode(
            "utf-8",
            errors="replace",
        ).strip()
        return {
            **base,
            "status": "LOCAL_TARGET_REF_UNAVAILABLE",
            "target_ref_status": "UNAVAILABLE_LOCALLY",
            "target_error": err or f"target_ref_not_found:{target_ref}",
            "answers": {
                "target_ref_available_locally": False,
                "remote_target_object_available": None,
                "review_required_before_reconcile": True,
                "can_reconcile_without_content_loss": False,
            },
            "next_actions": ["make_approved_target_ref_available_in_local_repo_before_remote_probe"],
        }
    target_commit = target_proc.stdout.decode("ascii", errors="replace").strip()
    target_tree = local_planner._git_text(local_repo_root, ["rev-parse", f"{target_commit}^{{tree}}"])

    try:
        remote_head = client.git_text(["rev-parse", "HEAD"], check=False)
        remote_origin_main = client.git_text(["rev-parse", "origin/main"], check=False)
        remote_target_object_available = _remote_target_available(client, target_commit)
    except (local_planner.GitCommandError, OSError, subprocess.TimeoutExpired) as exc:
        return {
            **base,
            "status": "REMOTE_GIT_UNAVAILABLE",
            "target_ref_status": "AVAILABLE_LOCALLY",
            "target_commit": target_commit,
            "target_tree": target_tree,
            "remote_error": str(exc),
            "answers": {
                "target_ref_available_locally": True,
                "remote_target_object_available": None,
                "review_required_before_reconcile": True,
                "can_reconcile_without_content_loss": False,
            },
            "next_actions": ["restore_or_repair_remote_source_checkout_before_remote_probe"],
        }

    status_bytes, status_error = _remote_git_status(client)
    if status_error or status_bytes is None:
        return {
            **base,
            "status": "REMOTE_STATUS_UNAVAILABLE",
            "target_ref_status": "AVAILABLE_LOCALLY",
            "target_commit": target_commit,
            "target_tree": target_tree,
            "remote_head": remote_head,
            "remote_origin_main": remote_origin_main,
            "remote_target_object_available": remote_target_object_available,
            "remote_error": status_error,
            "answers": {
                "target_ref_available_locally": True,
                "remote_target_object_available": remote_target_object_available,
                "review_required_before_reconcile": True,
                "can_reconcile_without_content_loss": False,
            },
            "next_actions": ["restore_or_repair_remote_source_checkout_before_reconcile_plan"],
        }

    entries = local_planner._parse_porcelain_z(status_bytes)
    classified = [
        _classify_remote_entry(
            local_repo_root,
            target_commit,
            client,
            entry,
            include_digests=include_digests,
        )
        for entry in entries
    ]

    classes_full: dict[str, list[dict[str, Any]]] = {
        key: [] for key in local_planner.CLASS_KEYS
    }
    for row in classified:
        classes_full.setdefault(str(row["classification"]), []).append(row)
    class_counts = {
        key: len(classes_full.get(key, [])) for key in local_planner.CLASS_KEYS
    }
    classes, class_truncated = _limit_classes(classes_full, max_paths_per_class)
    review_rows = [row for row in classified if row.get("review_required") is True]
    content_equivalent_rows = [
        row
        for row in classified
        if row.get("classification")
        in {
            "tracked_dirty_equals_target",
            "tracked_absent_equals_target_absent",
            "untracked_equals_target",
        }
    ]

    dirty_path_count = len(classified)
    review_required = bool(review_rows)
    remote_head_equals_target = bool(remote_head and remote_head == target_commit)

    if dirty_path_count == 0 and remote_head_equals_target:
        status = "REMOTE_SOURCE_CLEAN_AT_TARGET"
    elif dirty_path_count == 0:
        status = "REMOTE_SOURCE_CLEAN_BUT_NOT_TARGET"
    elif review_required:
        status = "REVIEW_REQUIRED_BEFORE_REMOTE_RECONCILE"
    else:
        status = "REMOTE_DIRTY_CONTENT_EQUIVALENT_TO_TARGET"

    if status == "REMOTE_SOURCE_CLEAN_AT_TARGET":
        next_actions = ["no_source_reconcile_required"]
    elif status == "REMOTE_SOURCE_CLEAN_BUT_NOT_TARGET":
        next_actions = ["operator_approve_fast_forward_or_checkout_remote_to_target_ref"]
    elif status == "REMOTE_DIRTY_CONTENT_EQUIVALENT_TO_TARGET":
        next_actions = [
            "operator_confirm_no_preserve_needed_for_content_equivalent_remote_dirty_paths",
            "operator_approve_runtime_source_reconcile_if_destructive_commands_are_needed",
            "rerun_remote_probe_after_reconcile",
        ]
    else:
        next_actions = [
            "operator_review_review_required_paths_before_any_remote_reset_or_clean",
            "archive_or_preserve_runtime_local_only_and_conflicting_paths",
            "rerun_remote_probe_after_preserve_or_reconcile_decision",
        ]
    if remote_target_object_available is False:
        next_actions.insert(
            0,
            "make_target_commit_available_on_runtime_under_operator_approval_before_direct_runtime_planner",
        )

    return {
        **base,
        "status": status,
        "target_ref_status": "AVAILABLE_LOCALLY",
        "target_commit": target_commit,
        "target_tree": target_tree,
        "remote_head": remote_head,
        "remote_origin_main": remote_origin_main,
        "remote_target_object_available": remote_target_object_available,
        "remote_head_equals_target": remote_head_equals_target,
        "dirty_path_count": dirty_path_count,
        "review_required_path_count": len(review_rows),
        "content_equivalent_path_count": len(content_equivalent_rows),
        "class_counts": class_counts,
        "class_truncated": class_truncated,
        "classes": classes,
        "review_required_paths": [row["path"] for row in review_rows],
        "content_equivalent_paths": [row["path"] for row in content_equivalent_rows],
        "answers": {
            "target_ref_available_locally": True,
            "remote_target_object_available": remote_target_object_available,
            "remote_worktree_has_dirty_or_untracked_paths": dirty_path_count > 0,
            "review_required_before_reconcile": review_required,
            "can_reconcile_without_content_loss": dirty_path_count > 0
            and not review_required,
            "operator_destructive_action_still_required": status
            in {
                "REMOTE_DIRTY_CONTENT_EQUIVALENT_TO_TARGET",
                "REVIEW_REQUIRED_BEFORE_REMOTE_RECONCILE",
                "REMOTE_SOURCE_CLEAN_BUT_NOT_TARGET",
            },
        },
        "next_actions": next_actions,
        "comparison_scope": (
            "Compares remote worktree file/symlink bytes read over SSH against "
            "local target tree blobs; remote target object is not required."
        ),
    }


def _render_human(plan: dict[str, Any]) -> str:
    lines = [
        f"status: {plan.get('status')}",
        f"remote_label: {plan.get('remote_label')}",
        f"remote_repo_root: {plan.get('remote_repo_root')}",
        f"target_ref: {plan.get('target_ref')} ({plan.get('target_commit')})",
        f"remote_head: {plan.get('remote_head')}",
        f"remote_target_object_available: {plan.get('remote_target_object_available')}",
        f"dirty_path_count: {plan.get('dirty_path_count', 0)}",
        f"review_required_path_count: {plan.get('review_required_path_count', 0)}",
        "class_counts:",
    ]
    for key, value in (plan.get("class_counts") or {}).items():
        if value:
            lines.append(f"  {key}: {value}")
    lines.append("next_actions:")
    for action in plan.get("next_actions") or []:
        lines.append(f"  - {action}")
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
    parser.add_argument(
        "--max-paths-per-class",
        type=int,
        default=50,
        help="cap emitted rows per classification bucket",
    )
    parser.add_argument(
        "--include-digests",
        action="store_true",
        help="include sha256 digests for compared remote/target bytes",
    )
    parser.add_argument("--human", action="store_true", help="print compact summary")
    parser.add_argument("--json-output", type=Path, default=None, help="optional local JSON output path")
    parser.add_argument(
        "--fail-on-review-required",
        action="store_true",
        help="exit nonzero when review is required or target/remote status is unavailable",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.remote_mode == "local":
        client: RemoteClient = LocalWorktreeClient(Path(args.remote_repo_root))
        remote_label = f"local:{args.remote_repo_root}"
    else:
        client = SshWorktreeClient(args.ssh_host, args.remote_repo_root)
        remote_label = f"ssh:{args.ssh_host}"

    plan = build_remote_plan(
        Path(args.local_repo_root),
        target_ref=args.target_ref,
        remote_repo_root=args.remote_repo_root,
        remote_label=remote_label,
        client=client,
        max_paths_per_class=max(args.max_paths_per_class, 0),
        include_digests=args.include_digests,
    )

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

    answers = plan.get("answers") or {}
    if args.fail_on_review_required and (
        plan.get("target_ref_status") != "AVAILABLE_LOCALLY"
        or plan.get("status") in {"REMOTE_GIT_UNAVAILABLE", "REMOTE_STATUS_UNAVAILABLE"}
        or answers.get("review_required_before_reconcile") is True
    ):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
