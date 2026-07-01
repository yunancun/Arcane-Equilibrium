#!/usr/bin/env python3
"""Classify source drift before retrying standing-envelope refresh.

This helper is source-only. It compares a previously reviewed source head with
the current source head and emits a fail-closed impact packet. It does not grant
approval, call runtime or Bybit, acquire a Decision Lease, write PG, mutate
services, or change risk/Cost Gate state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "standing_envelope_source_impact_guard_v1"

READY_STATUS = "STANDING_ENVELOPE_SOURCE_IMPACT_READY_FOR_E3_BB_REVIEW"
BLOCKED_STATUS = "STANDING_ENVELOPE_SOURCE_IMPACT_BLOCKED"

ACTIVE_BLOCKER_ID = "P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-SOURCE-STABILITY-CURRENT-HEAD"

BOUNDARY = (
    "source-impact guard only; no approval, no runtime call, no Control API GET, "
    "no exchange/public/private/order endpoint, no Decision Lease acquire/release, "
    "no order/cancel/modify, no PG query/write, no service/env/risk mutation, no "
    "Cost Gate change, no live/mainnet authority, no fill/PnL, and no proof"
)

SELF_TOOLING_PATHS = {
    "helper_scripts/research/cost_gate_learning_lane/standing_envelope_source_impact_guard.py",
    "helper_scripts/research/tests/test_standing_envelope_source_impact_guard.py",
    "helper_scripts/SCRIPT_INDEX.md",
}

DOC_PATH_PREFIXES = (
    "docs/",
)

POLICY_SENSITIVE_PATHS = {
    "AGENTS.md",
    "CLAUDE.md",
    "TODO.md",
}

POLICY_SENSITIVE_PREFIXES = (
    ".codex/",
    ".claude/",
    "docs/agents/",
    "docs/adr/",
    "docs/decisions/",
    "docs/runbooks/",
)

TEST_PATH_MARKERS = (
    "/tests/",
    "/test/",
)

PROTECTED_PREFIX_REASONS = (
    ("helper_scripts/research/cost_gate_learning_lane/", "cost_gate_learning_lane_surface_changed"),
    ("helper_scripts/cron/", "runtime_cron_surface_changed"),
    ("helper_scripts/deploy/", "runtime_deploy_surface_changed"),
    ("helper_scripts/systemd/", "runtime_service_surface_changed"),
    ("helper_scripts/security/", "runtime_security_surface_changed"),
    (
        "program_code/exchange_connectors/bybit_connector/",
        "bybit_connector_surface_changed",
    ),
    ("rust/openclaw_core/src/", "rust_production_surface_changed"),
    ("rust/openclaw_engine/src/", "rust_production_surface_changed"),
    ("rust/openclaw_types/src/", "rust_production_surface_changed"),
    ("rust/schemas/", "rust_schema_surface_changed"),
    ("settings/", "runtime_settings_surface_changed"),
    ("sql/", "database_schema_surface_changed"),
    (".github/workflows/", "ci_runtime_policy_surface_changed"),
    ("docker_projects/trading_services/", "runtime_service_config_surface_changed"),
    ("docker_projects/", "runtime_service_config_surface_changed"),
)

RUNTIME_SCRIPT_PATHS = {
    "helper_scripts/restart_all.sh",
    "helper_scripts/stop_all.sh",
    "helper_scripts/clean_restart.sh",
    "helper_scripts/fresh_start.sh",
    "helper_scripts/start_paper_trading.sh",
    "helper_scripts/cron_observer_cycle.sh",
    "helper_scripts/cron_daily_report.sh",
}

DEPENDENCY_OR_CONFIG_SUFFIXES = (
    "Cargo.toml",
    "Cargo.lock",
    "requirements.txt",
    "requirements-dev.txt",
    "poetry.lock",
    "Pipfile.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_dt(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _run_git(repo_root: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _git_stdout(repo_root: Path, args: list[str]) -> str:
    return _run_git(repo_root, args).stdout.strip()


def _try_git_stdout(
    repo_root: Path, args: list[str], error_key: str, errors: list[dict[str, str]]
) -> str | None:
    result = _run_git(repo_root, args, check=False)
    if result.returncode != 0:
        errors.append(
            {
                "key": error_key,
                "command": "git " + " ".join(args),
                "stderr": result.stderr.strip(),
            }
        )
        return None
    return result.stdout.strip()


def _parse_name_status(output: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0]
        paths = parts[1:]
        changes.append({"status": status, "paths": paths, "raw": raw_line})
    return changes


def _binary_paths_from_numstat(output: str) -> set[str]:
    paths: set[str] = set()
    for raw_line in output.splitlines():
        parts = raw_line.split("\t")
        if len(parts) < 3:
            continue
        if parts[0] == "-" or parts[1] == "-":
            paths.update(parts[2:])
    return paths


def collect_git_impact_inputs(
    repo_root: Path,
    *,
    base_source_head: str,
    current_source_head: str = "HEAD",
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    git_errors: list[dict[str, str]] = []
    resolved_base = _try_git_stdout(
        repo_root, ["rev-parse", base_source_head], "base_ref_unresolved", git_errors
    )
    resolved_current = _try_git_stdout(
        repo_root, ["rev-parse", current_source_head], "current_ref_unresolved", git_errors
    )
    head = _try_git_stdout(repo_root, ["rev-parse", "HEAD"], "head_ref_unresolved", git_errors)
    origin_main = _try_git_stdout(
        repo_root, ["rev-parse", "origin/main"], "origin_main_ref_unresolved", git_errors
    )
    status_short_branch = _try_git_stdout(
        repo_root, ["status", "--short", "--branch"], "git_status_failed", git_errors
    ) or ""
    status_lines = [line for line in status_short_branch.splitlines() if line.strip()]
    dirty_paths = [line for line in status_lines[1:] if line.strip()]
    ancestor_returncode: int | None = None
    diff_output = ""
    binary_paths: set[str] = set()
    if resolved_base and resolved_current:
        ancestor = _run_git(
            repo_root,
            ["merge-base", "--is-ancestor", resolved_base, resolved_current],
            check=False,
        )
        ancestor_returncode = ancestor.returncode
        diff_result = _run_git(
            repo_root,
            ["diff", "--name-status", f"{resolved_base}..{resolved_current}"],
            check=False,
        )
        if diff_result.returncode != 0:
            git_errors.append(
                {
                    "key": "git_diff_name_status_failed",
                    "command": f"git diff --name-status {resolved_base}..{resolved_current}",
                    "stderr": diff_result.stderr.strip(),
                }
            )
        else:
            diff_output = diff_result.stdout.strip()
        numstat_result = _run_git(
            repo_root,
            ["diff", "--numstat", f"{resolved_base}..{resolved_current}"],
            check=False,
        )
        if numstat_result.returncode != 0:
            git_errors.append(
                {
                    "key": "git_diff_numstat_failed",
                    "command": f"git diff --numstat {resolved_base}..{resolved_current}",
                    "stderr": numstat_result.stderr.strip(),
                }
            )
        else:
            binary_paths = _binary_paths_from_numstat(numstat_result.stdout)
    return {
        "collected_at_utc": _iso(now),
        "repo_root": str(repo_root),
        "base_source_head": resolved_base,
        "current_source_head": resolved_current,
        "head": head,
        "origin_main": origin_main,
        "status_short_branch": status_short_branch,
        "worktree_clean": not dirty_paths,
        "dirty_paths": dirty_paths,
        "base_is_ancestor_of_current": ancestor_returncode == 0,
        "changed_paths": [
            {**change, "binary_or_submodule_ambiguous": any(p in binary_paths for p in change.get("paths", []))}
            for change in _parse_name_status(diff_output)
        ],
        "git_errors": git_errors,
    }


def _path_is_test_only(path: str) -> bool:
    return any(marker in path for marker in TEST_PATH_MARKERS) or path.endswith("_test.rs")


def _path_is_docs_only(path: str) -> bool:
    return path.startswith(DOC_PATH_PREFIXES)


def classify_changed_path(path: str) -> dict[str, Any]:
    normalized = path.strip()
    if normalized in SELF_TOOLING_PATHS:
        return {
            "path": normalized,
            "category": "source_impact_guard_tooling",
            "impacts_standing_envelope_refresh_surface": False,
            "blocker": None,
        }
    if normalized in POLICY_SENSITIVE_PATHS or normalized.startswith(POLICY_SENSITIVE_PREFIXES):
        return {
            "path": normalized,
            "category": "policy_sensitive_context_changed",
            "impacts_standing_envelope_refresh_surface": True,
            "blocker": "policy_sensitive_context_changed",
        }
    if _path_is_docs_only(normalized):
        return {
            "path": normalized,
            "category": "documentation_or_todo",
            "impacts_standing_envelope_refresh_surface": False,
            "blocker": None,
        }
    if _path_is_test_only(normalized):
        return {
            "path": normalized,
            "category": "test_only",
            "impacts_standing_envelope_refresh_surface": False,
            "blocker": None,
        }
    if normalized in RUNTIME_SCRIPT_PATHS:
        return {
            "path": normalized,
            "category": "runtime_script_surface_changed",
            "impacts_standing_envelope_refresh_surface": True,
            "blocker": "runtime_script_surface_changed",
        }
    if normalized.endswith(DEPENDENCY_OR_CONFIG_SUFFIXES):
        return {
            "path": normalized,
            "category": "dependency_or_config_surface_changed",
            "impacts_standing_envelope_refresh_surface": True,
            "blocker": "dependency_or_config_surface_changed",
        }
    for prefix, reason in PROTECTED_PREFIX_REASONS:
        if normalized.startswith(prefix):
            return {
                "path": normalized,
                "category": reason,
                "impacts_standing_envelope_refresh_surface": True,
                "blocker": reason,
            }
    if normalized.startswith("rust/") and not _path_is_test_only(normalized):
        return {
            "path": normalized,
            "category": "rust_non_test_surface_changed",
            "impacts_standing_envelope_refresh_surface": True,
            "blocker": "rust_non_test_surface_changed",
        }
    return {
        "path": normalized,
        "category": "unclassified_source_change",
        "impacts_standing_envelope_refresh_surface": True,
        "blocker": "unclassified_source_change",
    }


def _classify_change(change: dict[str, Any]) -> list[dict[str, Any]]:
    paths = change.get("paths") or []
    if not isinstance(paths, list):
        paths = []
    classified = []
    for path in paths:
        item = classify_changed_path(str(path))
        item["change_status"] = change.get("status")
        if change.get("binary_or_submodule_ambiguous") is True:
            item["category"] = "binary_or_submodule_change_ambiguous"
            item["impacts_standing_envelope_refresh_surface"] = True
            item["blocker"] = "binary_or_submodule_change_ambiguous"
        classified.append(item)
    if not classified:
        classified.append(
            {
                "path": None,
                "category": "diff_entry_missing_path",
                "impacts_standing_envelope_refresh_surface": True,
                "blocker": "diff_entry_missing_path",
                "change_status": change.get("status"),
            }
        )
    return classified


def build_standing_envelope_source_impact_guard(
    *,
    git_inputs: dict[str, Any],
    active_blocker_id: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    blocker_id = str(active_blocker_id or ACTIVE_BLOCKER_ID).strip() or ACTIVE_BLOCKER_ID
    blockers: list[str] = []

    head = str(git_inputs.get("head") or "").strip()
    origin_main = str(git_inputs.get("origin_main") or "").strip()
    current = str(git_inputs.get("current_source_head") or "").strip()
    base = str(git_inputs.get("base_source_head") or "").strip()

    if not base:
        blockers.append("base_source_head_missing")
    if not current:
        blockers.append("current_source_head_missing")
    if not head or not origin_main:
        blockers.append("head_or_origin_main_missing")
    elif head != origin_main:
        blockers.append("head_origin_mismatch")
    if current and head and current != head:
        blockers.append("current_source_head_not_checked_out_head")
    if git_inputs.get("worktree_clean") is not True:
        blockers.append("worktree_dirty")
    if git_inputs.get("base_is_ancestor_of_current") is not True:
        blockers.append("base_not_ancestor_of_current")
    for error in git_inputs.get("git_errors") or []:
        if isinstance(error, dict):
            key = str(error.get("key") or "git_error")
            blockers.append(key)
        else:
            blockers.append("git_error")

    changed_paths = git_inputs.get("changed_paths") or []
    if not isinstance(changed_paths, list):
        changed_paths = []
        blockers.append("changed_paths_not_list")

    classifications: list[dict[str, Any]] = []
    for change in changed_paths:
        if not isinstance(change, dict):
            classifications.append(
                {
                    "path": None,
                    "category": "diff_entry_not_object",
                    "impacts_standing_envelope_refresh_surface": True,
                    "blocker": "diff_entry_not_object",
                }
            )
            continue
        classifications.extend(_classify_change(change))

    impact_blockers = sorted(
        {
            str(item.get("blocker"))
            for item in classifications
            if item.get("blocker")
        }
    )
    blockers.extend(impact_blockers)

    docs_or_tests_only = bool(classifications) and all(
        item.get("category")
        in {"documentation_or_todo", "test_only", "source_impact_guard_tooling"}
        for item in classifications
    )
    ready = not blockers
    status = READY_STATUS if ready else BLOCKED_STATUS
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _iso(now),
        "active_blocker_id": blocker_id,
        "status": status,
        "reason": (
            "source_drift_does_not_touch_standing_envelope_refresh_surface"
            if ready
            else "source_drift_impact_not_safe_for_standing_envelope_refresh"
        ),
        "boundary": BOUNDARY,
        "source_state": {
            "base_source_head": base or None,
            "current_source_head": current or None,
            "head": head or None,
            "origin_main": origin_main or None,
            "worktree_clean": git_inputs.get("worktree_clean") is True,
            "dirty_paths": git_inputs.get("dirty_paths") or [],
            "base_is_ancestor_of_current": git_inputs.get("base_is_ancestor_of_current")
            is True,
            "status_short_branch": git_inputs.get("status_short_branch"),
        },
        "changed_path_count": len(classifications),
        "changed_path_classifications": classifications,
        "git_errors": git_inputs.get("git_errors") or [],
        "docs_or_tests_or_guard_tooling_only": docs_or_tests_only,
        "blockers": blockers,
        "answers": {
            "source_impact_ready_for_e3_bb_review": ready,
            "standing_envelope_refresh_surface_unchanged": ready,
            "approval_granted_by_this_packet": False,
            "runtime_call_performed": False,
            "control_api_get_performed": False,
            "bybit_call_performed": False,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "service_restart_performed": False,
            "risk_mutation_performed": False,
            "cost_gate_change_performed": False,
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "promotion_proof": False,
            "profit_proof": False,
        },
        "max_safe_next_action": (
            "REQUEST_E3_BB_WITH_SOURCE_IMPACT_PACKET_NO_RUNTIME_ACTION"
            if ready
            else "REGENERATE_CURRENT_HEAD_REVIEW_OR_RESOLVE_IMPACT_BLOCKERS_NO_RUNTIME_ACTION"
        ),
    }


def render_markdown(packet: dict[str, Any]) -> str:
    source = packet.get("source_state") or {}
    return "\n".join(
        [
            "# Standing Envelope Source Impact Guard",
            "",
            f"- Status: `{packet.get('status')}`",
            f"- Active blocker: `{packet.get('active_blocker_id')}`",
            f"- Base source head: `{source.get('base_source_head')}`",
            f"- Current source head: `{source.get('current_source_head')}`",
            f"- HEAD: `{source.get('head')}`",
            f"- Origin main: `{source.get('origin_main')}`",
            f"- Worktree clean: `{source.get('worktree_clean')}`",
            f"- Changed path count: `{packet.get('changed_path_count')}`",
            f"- Docs/tests/tooling only: `{packet.get('docs_or_tests_or_guard_tooling_only')}`",
            f"- Blockers: `{packet.get('blockers')}`",
            "",
            packet.get("boundary") or "",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a source-impact guard for standing-envelope refresh."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--base-source-head", "--approved-base-ref", dest="base_source_head", required=True)
    parser.add_argument("--current-source-head", "--current-ref", dest="current_source_head", default="HEAD")
    parser.add_argument("--required-current-origin-main")
    parser.add_argument("--active-blocker-id", default=ACTIVE_BLOCKER_ID)
    parser.add_argument("--now-utc")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    now = _parse_dt(args.now_utc) if args.now_utc else _utc_now()
    if now is None:
        raise SystemExit("--now-utc must be an ISO-8601 timestamp")
    git_inputs = collect_git_impact_inputs(
        args.repo_root.resolve(),
        base_source_head=args.base_source_head,
        current_source_head=args.current_source_head,
        now_utc=now,
    )
    packet = build_standing_envelope_source_impact_guard(
        git_inputs=git_inputs,
        active_blocker_id=args.active_blocker_id,
        now_utc=now,
    )
    if args.required_current_origin_main:
        required = args.required_current_origin_main.strip()
        source = packet.get("source_state") or {}
        if source.get("origin_main") != required:
            packet["status"] = BLOCKED_STATUS
            packet["reason"] = "source_drift_impact_not_safe_for_standing_envelope_refresh"
            packet["blockers"] = sorted(
                set([*packet.get("blockers", []), "required_current_origin_main_mismatch"])
            )
            packet["answers"]["source_impact_ready_for_e3_bb_review"] = False
            packet["answers"]["standing_envelope_refresh_surface_unchanged"] = False
            packet["max_safe_next_action"] = (
                "REGENERATE_CURRENT_HEAD_REVIEW_OR_RESOLVE_IMPACT_BLOCKERS_NO_RUNTIME_ACTION"
            )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
