#!/usr/bin/env python3
"""Classify source drift before retrying standing-envelope refresh.

This helper is source-only. It compares a previously reviewed source head with
the current source head and emits a fail-closed impact packet. It does not grant
approval, call runtime or Bybit, acquire a Decision Lease, write PG, mutate
services, or change risk/Cost Gate state.

2026-07-03 修復（E2 temp-repo 實證三個假陰性）：舊採集只靠帶 rename 偵測的
`git diff --numstat` 中的 "-" 行比對 name-status 路徑——(a) binary rename 的
numstat 行是 curly-brace 合併路徑，與 name-status 兩端永不相等，flag 永不觸發；
(b) 裸 gitlink（mode 160000）numstat 給行數而非 "-"，根本不觸 binary 偵測；
(c) symlink（mode 120000）同樣以行數呈現、按路徑分類。三者落在 docs/ 等豁免樹
即假陰性放行。修法＝`--numstat --no-renames`（rename 兩端各自以原始路徑出現）
加上 `git diff --raw` mode 白名單（SAFE_FILE_MODES 之外任一端一律 ambiguous），
並加 unmatched 安全網：三路輸出對不上時以 git_errors blocker 收斂，不默默放行。
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

# git file mode 白名單：000000（不存在端）/ 100644（一般檔）/ 100755（可執行檔）。
# 為什麼採白名單而非黑名單：160000 gitlink 與 120000 symlink 之外，任何未知或
# 未來新增的 mode 也代表內容超出本 repo 可審範圍，deny-by-default 才 fail-closed。
SAFE_FILE_MODES = {"000000", "100644", "100755"}


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
    """從 numstat 輸出取 binary（"-" 行）路徑集合。

    為什麼呼叫端必須帶 `--no-renames`：帶 rename 偵測時 binary rename 行是
    curly-brace 合併路徑（`docs/{a.png => b.png}`），與 name-status 兩端路徑
    永不相等，flag 永不觸發（E2 2026-07-03 實證假陰性）。
    """
    paths: set[str] = set()
    for raw_line in output.splitlines():
        parts = raw_line.split("\t")
        if len(parts) < 3:
            continue
        if parts[0] == "-" or parts[1] == "-":
            paths.update(parts[2:])
    return paths


def _parse_raw_diff_line(line: str) -> dict[str, Any] | None:
    """解析 `git diff --raw` 單行：`:<src_mode> <dst_mode> <src_sha> <dst_sha> <status>\\t<path>[\\t<path2>]`。"""
    if not line.startswith(":"):
        return None
    head, *paths = line.split("\t")
    fields = head[1:].split(" ")
    if len(fields) < 5 or not paths:
        return None
    return {
        "src_mode": fields[0],
        "dst_mode": fields[1],
        "status": fields[4],
        "paths": [p for p in paths if p],
    }


def _unmatched_flagged_paths(
    flagged_paths: set[str], changes: list[dict[str, Any]]
) -> list[str]:
    """回傳未被任何 name-status 條目覆蓋的 flagged 路徑（排序後）。

    為什麼 fail-closed：numstat / --raw / name-status 三路輸出理應同源一致；
    對不上代表 rename、引號或編碼形態超出已知契約，若默默丟棄該路徑，
    binary/gitlink/symlink 歧義就會漏標、被路徑分類（如 docs/ 豁免）放行。
    """
    covered: set[str] = set()
    for change in changes:
        covered.update(str(p) for p in change.get("paths") or [])
    return sorted(p for p in flagged_paths if p not in covered)


def collect_git_impact_inputs(
    repo_root: Path,
    *,
    base_source_head: str,
    current_source_head: str = "HEAD",
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """採集 base..current 的 git 影響面輸入（name-status + numstat + raw 三路）。

    為什麼三路並收：name-status 給路徑與狀態；`--numstat --no-renames` 給可靠的
    binary 集合（rename 兩端各自以原始路徑出現）；`--raw` 給 mode bits，任一端
    mode 不在 SAFE_FILE_MODES（gitlink/symlink/未知 mode）即 ambiguous。任何一路
    採集失敗、解析失敗或三路對不上，都以 git_errors 傳導成 build 端 blocker。
    """
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
    ambiguous_mode_paths: set[str] = set()
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
        # 必須帶 --no-renames：見 _binary_paths_from_numstat docstring（binary
        # rename curly-brace 路徑假陰性）。
        numstat_result = _run_git(
            repo_root,
            ["diff", "--numstat", "--no-renames", f"{resolved_base}..{resolved_current}"],
            check=False,
        )
        if numstat_result.returncode != 0:
            git_errors.append(
                {
                    "key": "git_diff_numstat_failed",
                    "command": f"git diff --numstat --no-renames {resolved_base}..{resolved_current}",
                    "stderr": numstat_result.stderr.strip(),
                }
            )
        else:
            binary_paths = _binary_paths_from_numstat(numstat_result.stdout)
        # mode-aware 採集：numstat 對 gitlink（160000）給行數而非 "-"、symlink
        # （120000）亦按行數呈現，兩者都不觸 binary 偵測（E2 2026-07-03 實證），
        # 必須從 --raw 的 mode bits 補攔。
        raw_result = _run_git(
            repo_root,
            ["diff", "--raw", f"{resolved_base}..{resolved_current}"],
            check=False,
        )
        if raw_result.returncode != 0:
            git_errors.append(
                {
                    "key": "git_diff_raw_failed",
                    "command": f"git diff --raw {resolved_base}..{resolved_current}",
                    "stderr": raw_result.stderr.strip(),
                }
            )
        else:
            for line in raw_result.stdout.splitlines():
                if not line.strip():
                    continue
                entry = _parse_raw_diff_line(line)
                if entry is None:
                    # 為什麼 fail-closed：解析不了的 raw 行代表 diff 形態超出
                    # 已知契約，不能假設它安全。
                    git_errors.append({"key": "git_diff_raw_parse_failed", "line": line})
                    continue
                if (
                    entry["src_mode"] not in SAFE_FILE_MODES
                    or entry["dst_mode"] not in SAFE_FILE_MODES
                ):
                    ambiguous_mode_paths.update(entry["paths"])
    changed_paths = [
        {
            **change,
            "binary_or_submodule_ambiguous": any(
                p in binary_paths or p in ambiguous_mode_paths
                for p in change.get("paths", [])
            ),
        }
        for change in _parse_name_status(diff_output)
    ]
    # unmatched 安全網：flagged 路徑若對不回任何 name-status 條目，per-change flag
    # 無處落地，必須升為 git_errors blocker，不得默默放行。
    unmatched = _unmatched_flagged_paths(binary_paths | ambiguous_mode_paths, changed_paths)
    if unmatched:
        git_errors.append(
            {
                "key": "binary_or_mode_path_unmatched",
                "paths": json.dumps(unmatched, ensure_ascii=False),
            }
        )
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
        "changed_paths": changed_paths,
        # debug 透明用途；build 端不依賴這兩鍵（只加鍵不改既有鍵語義）。
        "binary_paths": sorted(binary_paths),
        "ambiguous_mode_paths": sorted(ambiguous_mode_paths),
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
