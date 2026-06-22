#!/usr/bin/env python3
"""Runtime source reconcile 的只讀規劃器。

用途：
- 在 operator 批准 runtime sync/reset/clean 之前，逐檔比對當前 dirty tree
  與目標 ref 的內容。
- 產出 machine-readable JSON，指出哪些本地改動已等價於 target，哪些仍需
  preserve / archive / 人工審查。

邊界：
- 只讀取 git metadata 和 worktree bytes。
- 不 fetch、不 pull、不 checkout、不 reset、不 clean、不 stash、不改 crontab、
  不改 env、不碰 DB/Bybit/order/risk/strategy。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "runtime_source_reconcile_plan_v1"
BOUNDARY = (
    "read-only git/worktree planner with optional explicit JSON artifact write; "
    "no fetch/pull/checkout/reset/clean/stash, no crontab/env/DB/Bybit/order/"
    "risk/strategy mutation"
)

CLASS_KEYS = (
    "tracked_dirty_equals_target",
    "tracked_absent_equals_target_absent",
    "tracked_dirty_differs_from_target",
    "tracked_missing_or_nonfile",
    "tracked_path_absent_from_target",
    "untracked_equals_target",
    "untracked_conflicts_with_target_path",
    "untracked_not_in_target",
    "unreadable_worktree_path",
)

REVIEW_REQUIRED_CLASSES = {
    "tracked_dirty_differs_from_target",
    "tracked_missing_or_nonfile",
    "tracked_path_absent_from_target",
    "untracked_conflicts_with_target_path",
    "untracked_not_in_target",
    "unreadable_worktree_path",
}


class GitCommandError(RuntimeError):
    """Git 指令失敗，保留 rc/stdout/stderr 供 JSON report 使用。"""

    def __init__(
        self,
        args: list[str],
        returncode: int,
        stdout: bytes = b"",
        stderr: bytes = b"",
    ) -> None:
        self.args_list = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        err = (stderr or stdout).decode("utf-8", errors="replace").strip()
        super().__init__(err or f"git rc={returncode}: {' '.join(args)}")


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _git(
    repo_root: Path,
    args: list[str],
    *,
    check: bool = True,
    timeout: int = 15,
) -> subprocess.CompletedProcess[bytes]:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise GitCommandError(args, proc.returncode, proc.stdout, proc.stderr)
    return proc


def _git_text(repo_root: Path, args: list[str], *, check: bool = True) -> str | None:
    proc = _git(repo_root, args, check=check)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="surrogateescape").strip()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_path(raw: bytes) -> str:
    return raw.decode("utf-8", errors="surrogateescape")


def _parse_porcelain_z(data: bytes) -> list[dict[str, str | None]]:
    entries: list[dict[str, str | None]] = []
    fields = data.split(b"\0")
    i = 0
    while i < len(fields):
        raw = fields[i]
        i += 1
        if not raw:
            continue
        if len(raw) < 4:
            status_code = _decode_path(raw[:2]).strip() or "UNKNOWN"
            path = _decode_path(raw[2:]).strip()
        else:
            status_code = _decode_path(raw[:2])
            path = _decode_path(raw[3:])
        old_path: str | None = None
        if status_code[:1] in {"R", "C"} or status_code[1:2] in {"R", "C"}:
            if i < len(fields):
                old_raw = fields[i]
                i += 1
                old_path = _decode_path(old_raw) if old_raw else None
        entries.append(
            {
                "status_code": status_code.strip() or "UNKNOWN",
                "path": path,
                "old_path": old_path,
            }
        )
    return entries


def _expand_untracked_entries(
    repo_root: Path,
    entries: list[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    expanded: list[dict[str, str | None]] = []
    for entry in entries:
        path_text = entry.get("path") or ""
        abs_path = repo_root / path_text
        if entry.get("status_code") == "??" and abs_path.is_dir():
            for child in sorted(abs_path.rglob("*")):
                if child.is_dir():
                    continue
                try:
                    rel = child.relative_to(repo_root).as_posix()
                except ValueError:
                    continue
                if rel.startswith(".git/"):
                    continue
                expanded.append({**entry, "path": rel})
            continue
        expanded.append(entry)
    return expanded


def _target_blob(repo_root: Path, target_commit: str, rel_path: str) -> bytes | None:
    proc = _git(repo_root, ["cat-file", "-e", f"{target_commit}:{rel_path}"], check=False)
    if proc.returncode != 0:
        return None
    return _git(repo_root, ["show", f"{target_commit}:{rel_path}"], check=True).stdout


def _target_mode(repo_root: Path, target_commit: str, rel_path: str) -> str | None:
    proc = _git(
        repo_root,
        ["ls-tree", "-z", target_commit, "--", rel_path],
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    first = proc.stdout.split(b"\0", 1)[0]
    meta = first.split(b"\t", 1)[0]
    return meta.split(b" ", 1)[0].decode("ascii", errors="replace")


def _worktree_bytes(repo_root: Path, rel_path: str) -> tuple[bytes | None, str | None, str | None]:
    path = repo_root / rel_path
    try:
        st = path.lstat()
    except FileNotFoundError:
        return None, "absent", None
    except OSError as exc:
        return None, "unreadable", f"{type(exc).__name__}:{exc}"

    mode = st.st_mode
    if stat.S_ISLNK(mode):
        try:
            return os.readlink(path).encode("utf-8", errors="surrogateescape"), "120000", None
        except OSError as exc:
            return None, "unreadable", f"{type(exc).__name__}:{exc}"
    if not stat.S_ISREG(mode):
        return None, "nonfile", None
    git_mode = "100755" if (mode & 0o111) else "100644"
    try:
        return path.read_bytes(), git_mode, None
    except OSError as exc:
        return None, "unreadable", f"{type(exc).__name__}:{exc}"


def _classify_entry(
    repo_root: Path,
    target_commit: str,
    entry: dict[str, str | None],
    *,
    include_digests: bool,
) -> dict[str, Any]:
    rel_path = entry.get("path") or ""
    status_code = entry.get("status_code") or "UNKNOWN"
    category = "untracked" if status_code == "??" else "tracked_change"
    target = _target_blob(repo_root, target_commit, rel_path)
    target_mode = _target_mode(repo_root, target_commit, rel_path)
    worktree, worktree_mode, worktree_error = _worktree_bytes(repo_root, rel_path)

    if worktree_error:
        classification = "unreadable_worktree_path"
        reason = worktree_error
    elif category == "tracked_change":
        if worktree_mode == "absent" and target is None:
            classification = "tracked_absent_equals_target_absent"
            reason = "worktree_path_absent_and_target_path_absent"
        elif worktree_mode in {"absent", "nonfile"}:
            classification = "tracked_missing_or_nonfile"
            reason = f"worktree_path_{worktree_mode}"
        elif target is None:
            classification = "tracked_path_absent_from_target"
            reason = "target_tree_has_no_matching_path"
        elif worktree == target:
            classification = "tracked_dirty_equals_target"
            reason = "worktree_content_equals_target_ref"
        else:
            classification = "tracked_dirty_differs_from_target"
            reason = "worktree_content_differs_from_target_ref"
    else:
        if worktree_mode in {"absent", "nonfile"}:
            classification = "unreadable_worktree_path"
            reason = f"untracked_worktree_path_{worktree_mode}"
        elif target is None:
            classification = "untracked_not_in_target"
            reason = "untracked_path_is_local_only_against_target_ref"
        elif worktree == target:
            classification = "untracked_equals_target"
            reason = "untracked_content_equals_target_ref"
        else:
            classification = "untracked_conflicts_with_target_path"
            reason = "untracked_content_differs_from_target_ref"

    row: dict[str, Any] = {
        "path": rel_path,
        "old_path": entry.get("old_path"),
        "status_code": status_code,
        "category": category,
        "classification": classification,
        "review_required": classification in REVIEW_REQUIRED_CLASSES,
        "reason": reason,
        "target_path_exists": target is not None,
        "target_mode": target_mode,
        "worktree_mode": worktree_mode,
        "mode_matches_target": (
            None
            if target_mode is None or worktree_mode in {None, "absent", "nonfile", "unreadable"}
            else target_mode == worktree_mode
        ),
    }
    if include_digests:
        row["target_sha256"] = _sha256_bytes(target) if target is not None else None
        row["worktree_sha256"] = _sha256_bytes(worktree) if worktree is not None else None
    return row


def _merge_base_is_ancestor(repo_root: Path, head: str | None, target_commit: str) -> bool | None:
    if not head:
        return None
    proc = _git(
        repo_root,
        ["merge-base", "--is-ancestor", head, target_commit],
        check=False,
    )
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


def _limit_classes(
    classes: dict[str, list[dict[str, Any]]],
    max_paths_per_class: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bool]]:
    limited: dict[str, list[dict[str, Any]]] = {}
    truncated: dict[str, bool] = {}
    for key in CLASS_KEYS:
        rows = classes.get(key, [])
        limited[key] = rows[:max_paths_per_class]
        truncated[key] = len(rows) > max_paths_per_class
    return limited, truncated


def build_plan(
    repo_root: Path,
    *,
    target_ref: str = "origin/main",
    max_paths_per_class: int = 50,
    include_digests: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now_iso(),
        "repo_root": str(repo_root),
        "target_ref": target_ref,
        "boundary": BOUNDARY,
        "mutated": False,
    }

    try:
        inside = _git_text(repo_root, ["rev-parse", "--is-inside-work-tree"])
    except (GitCommandError, OSError, subprocess.TimeoutExpired) as exc:
        return {
            **base,
            "status": "GIT_REPO_UNAVAILABLE",
            "target_ref_status": "UNKNOWN",
            "git_error": str(exc),
            "answers": {
                "target_ref_available": False,
                "review_required_before_reconcile": True,
                "can_reconcile_without_content_loss": False,
            },
            "next_actions": ["restore_or_repair_runtime_source_checkout_before_planning"],
        }
    if inside != "true":
        return {
            **base,
            "status": "GIT_REPO_UNAVAILABLE",
            "target_ref_status": "UNKNOWN",
            "git_error": "not_inside_work_tree",
            "answers": {
                "target_ref_available": False,
                "review_required_before_reconcile": True,
                "can_reconcile_without_content_loss": False,
            },
            "next_actions": ["restore_or_repair_runtime_source_checkout_before_planning"],
        }

    head = _git_text(repo_root, ["rev-parse", "HEAD"], check=False)
    target_proc = _git(
        repo_root,
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
            "status": "TARGET_REF_UNAVAILABLE",
            "target_ref_status": "UNAVAILABLE",
            "head": head,
            "target_commit": None,
            "target_tree": None,
            "target_error": err or f"target_ref_not_found:{target_ref}",
            "answers": {
                "target_ref_available": False,
                "review_required_before_reconcile": True,
                "can_reconcile_without_content_loss": False,
            },
            "class_counts": {key: 0 for key in CLASS_KEYS},
            "classes": {key: [] for key in CLASS_KEYS},
            "next_actions": [
                "sync_or_fetch_target_ref_under_operator_approval_before_reconcile_plan"
            ],
        }

    target_commit = target_proc.stdout.decode("ascii", errors="replace").strip()
    target_tree = _git_text(repo_root, ["rev-parse", f"{target_commit}^{{tree}}"])
    status_bytes = _git(
        repo_root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        check=True,
    ).stdout
    status_entries = _expand_untracked_entries(repo_root, _parse_porcelain_z(status_bytes))
    classified = [
        _classify_entry(
            repo_root,
            target_commit,
            entry,
            include_digests=include_digests,
        )
        for entry in status_entries
    ]

    classes_full: dict[str, list[dict[str, Any]]] = {key: [] for key in CLASS_KEYS}
    for row in classified:
        classes_full.setdefault(str(row["classification"]), []).append(row)
    class_counts = {key: len(classes_full.get(key, [])) for key in CLASS_KEYS}
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
    head_ancestor_of_target = _merge_base_is_ancestor(repo_root, head, target_commit)
    head_equals_target = bool(head and head == target_commit)

    if dirty_path_count == 0 and head_equals_target:
        status = "SOURCE_CLEAN_AT_TARGET"
    elif dirty_path_count == 0:
        status = "SOURCE_CLEAN_BUT_NOT_TARGET"
    elif review_required:
        status = "REVIEW_REQUIRED_BEFORE_RECONCILE"
    else:
        status = "DIRTY_CONTENT_EQUIVALENT_TO_TARGET"

    next_actions: list[str]
    if status == "SOURCE_CLEAN_AT_TARGET":
        next_actions = ["no_source_reconcile_required"]
    elif status == "SOURCE_CLEAN_BUT_NOT_TARGET":
        next_actions = ["operator_approve_fast_forward_or_checkout_to_target_ref"]
    elif status == "DIRTY_CONTENT_EQUIVALENT_TO_TARGET":
        next_actions = [
            "operator_confirm_no_preserve_needed_for_content_equivalent_dirty_paths",
            "operator_approve_runtime_source_reconcile_if_destructive_commands_are_needed",
            "rerun_planner_after_reconcile",
        ]
    else:
        next_actions = [
            "operator_review_review_required_paths_before_any_reset_or_clean",
            "archive_or_preserve_runtime_local_only_and_conflicting_paths",
            "rerun_planner_after_preserve_or_reconcile_decision",
        ]
    if head_ancestor_of_target is False:
        next_actions.insert(0, "review_local_head_not_ancestor_of_target_before_sync")

    return {
        **base,
        "status": status,
        "target_ref_status": "AVAILABLE",
        "head": head,
        "target_commit": target_commit,
        "target_tree": target_tree,
        "head_equals_target": head_equals_target,
        "head_ancestor_of_target": head_ancestor_of_target,
        "dirty_path_count": dirty_path_count,
        "review_required_path_count": len(review_rows),
        "content_equivalent_path_count": len(content_equivalent_rows),
        "class_counts": class_counts,
        "class_truncated": class_truncated,
        "classes": classes,
        "review_required_paths": [row["path"] for row in review_rows],
        "content_equivalent_paths": [row["path"] for row in content_equivalent_rows],
        "answers": {
            "target_ref_available": True,
            "worktree_has_dirty_or_untracked_paths": dirty_path_count > 0,
            "review_required_before_reconcile": review_required,
            "can_reconcile_without_content_loss": dirty_path_count > 0
            and not review_required,
            "operator_destructive_action_still_required": status
            in {
                "DIRTY_CONTENT_EQUIVALENT_TO_TARGET",
                "REVIEW_REQUIRED_BEFORE_RECONCILE",
                "SOURCE_CLEAN_BUT_NOT_TARGET",
            },
        },
        "next_actions": next_actions,
        "comparison_scope": (
            "Compares worktree file/symlink bytes against target tree blobs; "
            "mode_matches_target is reported separately."
        ),
    }


def _render_human(plan: dict[str, Any]) -> str:
    lines = [
        f"status: {plan.get('status')}",
        f"repo_root: {plan.get('repo_root')}",
        f"target_ref: {plan.get('target_ref')} ({plan.get('target_commit')})",
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
    parser.add_argument("--repo-root", default=".", help="git repo root to inspect")
    parser.add_argument("--target-ref", default="origin/main", help="local target ref/sha")
    parser.add_argument(
        "--max-paths-per-class",
        type=int,
        default=50,
        help="cap emitted rows per classification bucket",
    )
    parser.add_argument(
        "--include-digests",
        action="store_true",
        help="include sha256 digests for compared worktree/target bytes",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="print compact human summary instead of JSON",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="optional path to also write the JSON plan",
    )
    parser.add_argument(
        "--fail-on-review-required",
        action="store_true",
        help="exit nonzero when the plan requires human review or target is unavailable",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    plan = build_plan(
        Path(args.repo_root),
        target_ref=args.target_ref,
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
    if args.fail_on_review_required and (
        plan.get("target_ref_status") != "AVAILABLE"
        or (plan.get("answers") or {}).get("review_required_before_reconcile") is True
    ):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
