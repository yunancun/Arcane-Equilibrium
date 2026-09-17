#!/usr/bin/env python3
"""Advisory publication diagnostics before admission; never grants authority."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from agent_governance_capture import (
    HEAD_RE,
    capture_native_linear_commit_range,
    native_origin_urls,
    native_remote_head,
    validate_public_github_repository_ref,
)
from agent_governance_task_admission import FileTaskAdmissionStore, workflow_delivery_key
from agent_governance_writer_lease import inspect_worktree
from git_loop_guard import inspect_repository


def _literal_path(value: str) -> bool:
    return (
        bool(value)
        and not any(c in value for c in "\\*?[]\x00\r\n")
        and all(part not in {"", ".", ".."} for part in value.split("/"))
        and not value.startswith("-")
    )


def _lifecycle(
    state: dict[str, Any], journal: dict[str, Any], *, key: str,
    worktree: str, owner: str, base: str, paths: list[str],
) -> tuple[dict[str, Any], list[str]]:
    """Project only non-secret fields; retain canonical readers' validation."""
    reasons: list[str] = []
    delivery = journal["deliveries"].get(key)
    held = state["admissions"].get(worktree)
    view: dict[str, Any] = {"state": "NEW_DELIVERY", "accepted_base": None}
    if delivery is None:
        if held is not None:
            reasons.append("WORKTREE_TASK_ADMISSION_HELD")
        return view, reasons
    if not set(paths).issubset(delivery["frozen_envelope"]["dirty_scope"]):
        reasons.append("DELIVERY_SCOPE_EXPANDED")
    history = delivery["admissions"]
    if history and owner != history[0]["owner"]:
        reasons.append("DELIVERY_OWNER_CHANGED")
    if delivery["pending_admission"] is not None:
        reasons.append("DELIVERY_STATE_AMBIGUOUS")
    active = [item for item in history if item["state"] in {"ACTIVE", "TERMINAL"}]
    if active:
        view["state"] = "EXISTING_ADMISSION"
        item = active[-1]
        record = state["admissions"].get(item["worktree"])
        if len(active) != 1 or record is None or any(
            record.get(field) != item.get(field)
            for field in ("admission_id", "task_id", "owner", "task_contract_digest", "accepted_base")
        ):
            reasons.append("DELIVERY_STATE_AMBIGUOUS")
        elif item["worktree"] != worktree or item["owner"] != owner:
            reasons.append("DELIVERY_ADMISSION_HELD")
        elif item["state"] != "ACTIVE" or record["state"] != "ACTIVE":
            reasons.append("DELIVERY_ADMISSION_NOT_ACTIVE")
        else:
            accepted = record.get("accepted_base") or {}
            view["accepted_base"] = accepted.get("head")
            if accepted.get("head") != base:
                reasons.append("ADMISSION_BASE_MISMATCH")
            if not set(paths).issubset(record["task_contract"]["dirty_scope"]):
                reasons.append("ADMISSION_SCOPE_MISMATCH")
    elif history:
        view["state"] = "RELEASED_DELIVERY"
        budget = delivery["repair_budget"]
        if not budget["authorized"] or budget["consumed"]:
            reasons.append("DELIVERY_REPAIR_NOT_AUTHORIZED")
        if held is not None:
            reasons.append("WORKTREE_TASK_ADMISSION_HELD")
    return view, reasons


def inspect_publication(
    repo: Path, *, expected_branch: str, expected_head: str, admission_base: str,
    allow_paths: list[str], work_item_id: str, lane_id: str, owner: str,
) -> dict[str, Any]:
    """Read a bounded local delivery snapshot and one live public main ref.

    READ_ONLY_READY means no covered diagnostic failed, not admission, review,
    CI, lease, or publication approval. All actual gates must still run.
    """
    reasons: list[str] = []
    result: dict[str, Any] = {
        "schema_version": "git_publication_preflight_v1",
        "status": "BLOCKED", "publication_authorized": False,
        "mutated_local": False, "mutated_remote": False,
        "expected_branch": expected_branch, "expected_head": expected_head,
        "proposed_admission_base": admission_base, "published_main": None,
        "scope": sorted(set(allow_paths)), "commits": [], "touched_paths": [],
        "out_of_scope_paths": [], "lifecycle": None, "reasons": reasons,
        "next_steps": [],
        "coverage_debt": [
            "Operator authorization and the full frozen task contract are not verified.",
            "Writer lease, review, CI and final publication gates remain mandatory.",
        ],
    }
    if not all(HEAD_RE.fullmatch(v) for v in (expected_head, admission_base)):
        reasons.append("INVALID_COMMIT_IDENTITY")
    if expected_branch == "main" or not validate_public_github_repository_ref(
        "https://github.com/placeholder/repository.git", "refs/heads/" + expected_branch
    ):
        reasons.append("INVALID_FEATURE_BRANCH")
    if not allow_paths or not all(_literal_path(p) for p in allow_paths):
        reasons.append("INVALID_LITERAL_SCOPE")
    if not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", v)
               for v in (work_item_id, lane_id, owner)):
        reasons.append("INVALID_DELIVERY_IDENTITY")
    if reasons:
        result["next_steps"] = ["Supply pinned full commit IDs, a feature branch, literal file paths and the existing delivery identity."]
        return result
    repo = repo.resolve()
    try:
        identity = inspect_worktree(repo, native_graph=True)
        local = inspect_repository(repo)
        if repo != Path(identity.worktree) or not identity.linked:
            reasons.append("LINKED_WORKTREE_REQUIRED")
        if identity.branch != expected_branch or local["branch"] != expected_branch:
            reasons.append("BRANCH_MISMATCH")
        if identity.head != expected_head or local["head"] != expected_head:
            reasons.append("HEAD_MISMATCH")
        if identity.dirty or local["dirty_paths"] or local["staged_paths"]:
            reasons.append("DIRTY_WORKTREE")
        reasons.extend(local["inspection_failures"])
        result["dirty_paths"] = local["dirty_paths"]
        store = FileTaskAdmissionStore(identity.common_dir)
        state, journal = store.read(), store.read_delivery_journal()
        key = workflow_delivery_key({
            "surfaces": ["current_workflow_state"],
            "work_item_id": work_item_id, "lane_id": lane_id,
        })
        view, lifecycle_reasons = _lifecycle(
            state, journal, key=key, worktree=identity.worktree,
            owner=owner, base=admission_base, paths=allow_paths,
        )
        result["lifecycle"] = view
        reasons.extend(lifecycle_reasons)
        # Pure allowlist validation must precede the remote producer callback.
        urls = native_origin_urls(repo)
        fetch, push = urls
        safe_origin = (len(fetch) == 1 and fetch == push
                       and validate_public_github_repository_ref(fetch[0], "refs/heads/main"))
        if not safe_origin:
            reasons.append("UNSAFE_ORIGIN")
        else:
            main = native_remote_head(repo, fetch[0], "refs/heads/main")
            if main is None or HEAD_RE.fullmatch(main) is None:
                reasons.append("PUBLISHED_MAIN_UNAVAILABLE")
            else:
                result["published_main"] = main
                if admission_base != main:
                    reasons.append("ADMISSION_BASE_NOT_PUBLISHED_MAIN")
                if local["local_origin_main"] != main:
                    reasons.append("REMOTE_TRACKING_STALE")
                if expected_head == main:
                    reasons.append("SOURCE_ALREADY_PUBLISHED")
        commits, patches, range_reasons = capture_native_linear_commit_range(
            repo, admission_base, expected_head,
        )
        reasons.extend(range_reasons)
        if admission_base == expected_head:
            reasons.append("ORDINARY_PUBLICATION_EMPTY_COMMIT_RANGE")
        result["commits"] = commits
        result["patch_digests"] = patches
        paths = sorted({path for commit in commits for path in commit["paths"]})
        result["touched_paths"] = paths
        result["out_of_scope_paths"] = sorted(set(paths) - set(allow_paths))
        if result["out_of_scope_paths"]:
            reasons.append("COMMIT_RANGE_OUT_OF_SCOPE")
        # Detect observed drift without locks, writes, repairs or fencing tokens.
        if (identity != inspect_worktree(repo, native_graph=True)
                or local != inspect_repository(repo) or urls != native_origin_urls(repo)
                or state != store.read() or journal != store.read_delivery_journal()):
            reasons.append("PREFLIGHT_STATE_CHANGED")
    except (ValueError, OSError):
        # Reader errors can contain local metadata; never emit raw exceptions.
        reasons.append("LOCAL_EVIDENCE_UNAVAILABLE_OR_AMBIGUOUS")
    result["reasons"] = sorted(set(reasons))
    if not reasons:
        result["status"] = "READ_ONLY_READY"
    steps = result["next_steps"]
    if "DELIVERY_REPAIR_NOT_AUTHORIZED" in reasons:
        steps.append("The delivery was released. Obtain explicit Operator continuation through the existing admission workflow; do not reset its journal or rename its IDs.")
    if "SOURCE_ALREADY_PUBLISHED" in reasons:
        steps.append("This exact source is already published. Verify adoption; do not create another publication range.")
    elif any(r in reasons for r in (
        "ORDINARY_PUBLICATION_EMPTY_COMMIT_RANGE", "ADMISSION_BASE_NOT_PUBLISHED_MAIN",
    )):
        steps.append("Preserve the reviewed checkout. After lifecycle blockers are resolved, admit a separate clean publication worktree at verified published main, then fast-forward to the reviewed source and run the original guards.")
    if "REMOTE_TRACKING_STALE" in reasons or "PUBLISHED_MAIN_UNAVAILABLE" in reasons:
        steps.append("Reconcile remote evidence separately under the existing workflow; this diagnostic never fetches or retries transport.")
    if reasons:
        steps.append("Resolve the listed blockers with their owner. Preserve dirty work and recheck the same pinned source; do not bypass admission or publication gates.")
    elif result["lifecycle"]["state"] == "EXISTING_ADMISSION":
        steps.append("Keep the matching admission. Verify the existing writer lease, exact-head review and CI, then run git_loop_guard.py publish and post-push.")
    else:
        steps.append("Preserve reviewed source. Use the existing admission workflow on a clean linked publication worktree at published main, fast-forward to this pinned head, then complete the original review, CI and publication gates.")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    for name in ("expected-branch", "expected-head", "admission-base", "work-item-id", "lane-id", "owner"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--allow-path", dest="allow_paths", action="append", required=True)
    parser.add_argument("--human", action="store_true")
    args = vars(parser.parse_args(argv))
    human = args.pop("human")
    result = inspect_publication(**args)
    if human:
        print(f"{result['status']} (advisory only; publication_authorized=false)")
        print(f"Source: {result['expected_head']}\nPublished main: {result['published_main']}\nAdmission base: {result['proposed_admission_base']}")
        print("Reasons: " + (", ".join(result["reasons"]) or "none in covered checks"))
        for commit in result["commits"]:
            print(f"Commit {commit['commit']}: " + json.dumps(commit["paths"], ensure_ascii=True))
        for step in result["next_steps"]:
            print("- " + step)
        for debt in result["coverage_debt"]:
            print("Not verified: " + debt)
    else:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "READ_ONLY_READY" else 3


if __name__ == "__main__":
    sys.exit(main())
