"""Immutable merged-PR and required-check proof for AIML adoption."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agent_governance_aiml_trusted_common import HEAD_RE, instant


def associated_pulls_path(
    repository: str, head: str, *, page: int, page_size: int,
) -> str:
    if HEAD_RE.fullmatch(head) is None or page < 1:
        raise ValueError("GitHub associated-PR request is invalid")
    return (
        f"/repos/{repository}/commits/{head}/pulls"
        f"?per_page={page_size}&page={page}"
    )


def pull_path(repository: str, number: int) -> str:
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ValueError("GitHub pull-request number is invalid")
    return f"/repos/{repository}/pulls/{number}"


def check_runs_path(
    repository: str, head: str, *, page: int, page_size: int,
) -> str:
    if HEAD_RE.fullmatch(head) is None or page < 1:
        raise ValueError("GitHub check-run request is invalid")
    return (
        f"/repos/{repository}/commits/{head}/check-runs"
        f"?filter=latest&per_page={page_size}&page={page}"
    )


def _repository_identity(value: Any) -> tuple[Any, Any]:
    return (
        value.get("id") if isinstance(value, dict) else None,
        value.get("full_name") if isinstance(value, dict) else None,
    )


def _pull_core(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("GitHub pull-request response is invalid")
    head = payload.get("head")
    base = payload.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict):
        raise ValueError("GitHub pull-request refs are missing")
    number = payload.get("number")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ValueError("GitHub pull-request number is invalid")
    head_repo_id, head_repo_name = _repository_identity(head.get("repo"))
    base_repo_id, base_repo_name = _repository_identity(base.get("repo"))
    return {
        "number": number,
        "state": payload.get("state"),
        "draft": payload.get("draft"),
        "merged_at": payload.get("merged_at"),
        "merge_commit_sha": payload.get("merge_commit_sha"),
        "head_sha": head.get("sha"),
        "head_repository_id": head_repo_id,
        "head_repository_full_name": head_repo_name,
        "base_ref": base.get("ref"),
        "base_repository_id": base_repo_id,
        "base_repository_full_name": base_repo_name,
    }


def associated_pulls_projection(
    payload: Any, *, page: int, projection_version: str,
) -> dict[str, Any]:
    if not isinstance(payload, list):
        raise ValueError("GitHub associated-PR response is invalid")
    items = [_pull_core(item) for item in payload]
    numbers = [item["number"] for item in items]
    if len(numbers) != len(set(numbers)):
        raise ValueError("GitHub associated-PR response contains duplicates")
    return {
        "projection_version": projection_version,
        "kind": "associated_pull_requests_page",
        "page": page,
        "items": sorted(items, key=lambda item: item["number"]),
    }


def pull_projection(payload: Any, *, projection_version: str) -> dict[str, Any]:
    core = _pull_core(payload)
    return {
        "projection_version": projection_version,
        "kind": "pull_request",
        **core,
        "merged": payload.get("merged"),
    }


def check_runs_projection(
    payload: Any, *, page: int, projection_version: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("check_runs"), list):
        raise ValueError("GitHub check-runs response is invalid")
    total = payload.get("total_count")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise ValueError("GitHub check-runs total_count is invalid")
    items = []
    for run in payload["check_runs"]:
        if not isinstance(run, dict) or not isinstance(run.get("app"), dict):
            raise ValueError("GitHub check-run item is malformed")
        pull_requests = run.get("pull_requests")
        if not isinstance(pull_requests, list):
            raise ValueError("GitHub check-run pull-request inventory is malformed")
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("number"), int)
            or isinstance(item.get("number"), bool)
            or item["number"] < 1
            for item in pull_requests
        ):
            raise ValueError("GitHub check-run pull-request item is malformed")
        items.append({
            "id": run.get("id"),
            "name": run.get("name"),
            "head_sha": run.get("head_sha"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "app_id": run["app"].get("id"),
            "started_at": run.get("started_at"),
            "completed_at": run.get("completed_at"),
            "pull_request_numbers": sorted(
                item["number"] for item in pull_requests
            ),
        })
    ids = [item["id"] for item in items]
    if any(not isinstance(value, int) or isinstance(value, bool) for value in ids):
        raise ValueError("GitHub check-run id is invalid")
    if len(ids) != len(set(ids)):
        raise ValueError("GitHub check-runs response contains duplicate ids")
    return {
        "projection_version": projection_version,
        "kind": "check_runs_page",
        "page": page,
        "total_count": total,
        "items": sorted(
            items, key=lambda item: (str(item["name"]), int(item["app_id"] or -1), item["id"])
        ),
    }


def select_merged_pull(
    pulls: list[dict[str, Any]], *, reviewed_head: str, merge_head: str,
    repository_id: int, repository_name: str, default_branch: str,
) -> dict[str, Any]:
    expected = {
        "state": "closed", "draft": False, "merge_commit_sha": merge_head,
        "head_sha": reviewed_head, "head_repository_id": repository_id,
        "head_repository_full_name": repository_name,
        "base_ref": default_branch, "base_repository_id": repository_id,
        "base_repository_full_name": repository_name,
    }
    matches = [
        pull for pull in pulls
        if all(pull.get(field) == value for field, value in expected.items())
        and isinstance(pull.get("merged_at"), str)
    ]
    if len(matches) != 1:
        raise ValueError("reviewed head lacks one exact merged pull request")
    return matches[0]


def verify_merged_pull_gate_outcomes(
    *, inventory_pull: dict[str, Any], pull: dict[str, Any],
    check_runs: list[dict[str, Any]], reviewed_head: str, merge_head: str,
    merge_parent_shas: list[str], required_checks: tuple[dict[str, Any], ...],
    observed_at: datetime, now: datetime,
) -> None:
    if pull != {"projection_version": pull.get("projection_version"),
                "kind": "pull_request", **inventory_pull, "merged": True}:
        raise ValueError("merged pull-request detail differs from association")
    if not (
        len(merge_parent_shas) == 2
        and merge_parent_shas[1] == reviewed_head
        and merge_parent_shas[0] not in {reviewed_head, merge_head}
    ):
        raise ValueError("merge commit does not directly parent the reviewed head")
    merged_at = instant(pull.get("merged_at"))
    if not merged_at <= observed_at <= now:
        raise ValueError("merged pull request is future-dated")
    for expected in required_checks:
        if (
            not isinstance(expected.get("integration_id"), int)
            or isinstance(expected.get("integration_id"), bool)
            or expected["integration_id"] < 1
        ):
            raise ValueError("required check integration binding is unsupported")
        matches = [
            run for run in check_runs
            if run.get("name") == expected["context"]
            and run.get("app_id") == expected["integration_id"]
        ]
        if len(matches) != 1:
            raise ValueError("required check result is missing or ambiguous")
        run = matches[0]
        started = instant(run.get("started_at"))
        completed = instant(run.get("completed_at"))
        if not (
            run.get("head_sha") == reviewed_head
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
            and started <= completed <= merged_at
            and completed <= now
        ):
            raise ValueError("required check did not succeed before merge")
        pull_numbers = run.get("pull_request_numbers")
        if pull_numbers and inventory_pull["number"] not in pull_numbers:
            raise ValueError("required check is associated with another pull request")
