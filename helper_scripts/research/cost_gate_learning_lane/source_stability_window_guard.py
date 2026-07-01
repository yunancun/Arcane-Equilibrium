#!/usr/bin/env python3
"""Build a source-stability window guard artifact before E3/BB review.

The guard is deliberately source-only. It does not fetch, call runtime,
contact Bybit, acquire or release a Decision Lease, write PG, mutate services,
or grant order/probe/live authority. The caller is responsible for running
`git fetch` before invoking this helper when remote freshness matters.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "source_stability_window_guard_v1"

READY_STATUS = "SOURCE_STABILITY_WINDOW_READY_FOR_E3_BB_REVIEW"
SAMPLE_STATUS = "SOURCE_STABILITY_WINDOW_SAMPLE_RECORDED_NO_APPROVAL"
BLOCKED_STATUS = "SOURCE_STABILITY_WINDOW_BLOCKED_BY_SOURCE_DRIFT"

ACTIVE_BLOCKER_ID = (
    "P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE"
)

BOUNDARY = (
    "source-stability guard only; no approval, no exchange call, no Decision "
    "Lease acquire/release, no Bybit private/order endpoint, no order/cancel/"
    "modify, no PG query/write, no runtime/service/env/risk mutation, no Cost "
    "Gate lowering, no live/mainnet authority, no fill/PnL, and no profit proof"
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


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"json object required: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def collect_source_state(repo_root: Path, *, now_utc: dt.datetime | None = None) -> dict[str, Any]:
    now = now_utc or _utc_now()
    revs = _run_git(repo_root, ["rev-parse", "HEAD", "origin/main"]).splitlines()
    if len(revs) != 2:
        raise RuntimeError("expected git rev-parse HEAD origin/main to return two lines")
    status = _run_git(repo_root, ["status", "--short", "--branch"])
    status_lines = [line for line in status.splitlines() if line.strip()]
    dirty_paths = [line for line in status_lines[1:] if line.strip()]
    return {
        "collected_at_utc": _iso(now),
        "repo_root": str(repo_root),
        "head": revs[0].strip(),
        "origin_main": revs[1].strip(),
        "status_short_branch": status,
        "worktree_clean": len(dirty_paths) == 0,
        "dirty_paths": dirty_paths,
    }


def _previous_source_state(previous: dict[str, Any] | None) -> dict[str, Any] | None:
    if not previous:
        return None
    source_state = previous.get("source_state")
    if isinstance(source_state, dict):
        return source_state
    head = previous.get("source_head")
    origin = previous.get("source_origin_main")
    generated = previous.get("generated_at_utc")
    if head or origin or generated:
        return {
            "collected_at_utc": generated,
            "head": head,
            "origin_main": origin,
            "worktree_clean": previous.get("worktree_clean"),
            "dirty_paths": previous.get("dirty_paths") or [],
        }
    return None


def build_source_stability_window_guard(
    *,
    current_source_state: dict[str, Any],
    previous_guard: dict[str, Any] | None = None,
    min_quiet_seconds: int = 60,
    required_source_head: str | None = None,
    required_origin_main: str | None = None,
    active_blocker_id: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    blocker_id = str(active_blocker_id or ACTIVE_BLOCKER_ID).strip()
    if not blocker_id:
        blocker_id = ACTIVE_BLOCKER_ID
    previous_source = _previous_source_state(previous_guard)
    blockers: list[str] = []
    if min_quiet_seconds <= 0:
        blockers.append("min_quiet_seconds_invalid")
    previous_schema_valid = (
        previous_guard is None or previous_guard.get("schema_version") == SCHEMA_VERSION
    )
    if not previous_schema_valid:
        blockers.append("previous_guard_schema_mismatch")
        previous_source = None
    elif previous_guard is not None and previous_source is None:
        blockers.append("previous_sample_missing_source_state")

    head = str(current_source_state.get("head") or "").strip()
    origin_main = str(current_source_state.get("origin_main") or "").strip()
    worktree_clean = current_source_state.get("worktree_clean") is True

    if not head or not origin_main:
        blockers.append("source_head_or_origin_missing")
    elif head != origin_main:
        blockers.append("head_origin_mismatch")

    if not worktree_clean:
        blockers.append("worktree_dirty")

    if required_source_head and head != required_source_head:
        blockers.append("required_source_head_mismatch")
    if required_origin_main and origin_main != required_origin_main:
        blockers.append("required_origin_main_mismatch")

    quiet_elapsed_seconds: float | None = None
    previous_summary: dict[str, Any] | None = None
    if previous_source is not None:
        previous_head = str(previous_source.get("head") or "").strip()
        previous_origin = str(previous_source.get("origin_main") or "").strip()
        previous_collected = _parse_dt(previous_source.get("collected_at_utc"))
        previous_worktree_clean = previous_source.get("worktree_clean") is True
        previous_dirty_paths = previous_source.get("dirty_paths") or []
        previous_summary = {
            "collected_at_utc": previous_source.get("collected_at_utc"),
            "head": previous_head or None,
            "origin_main": previous_origin or None,
            "worktree_clean": previous_worktree_clean,
            "dirty_paths": previous_dirty_paths,
        }
        if not previous_worktree_clean or previous_dirty_paths:
            blockers.append("previous_sample_worktree_dirty")
        if previous_head != head:
            blockers.append("previous_source_head_mismatch")
        if previous_origin != origin_main:
            blockers.append("previous_origin_main_mismatch")
        if previous_collected is None:
            blockers.append("previous_sample_timestamp_invalid")
        else:
            quiet_elapsed_seconds = max(0.0, (now - previous_collected).total_seconds())
            if quiet_elapsed_seconds < min_quiet_seconds:
                blockers.append("quiet_window_not_elapsed")

    if previous_source is None and blockers:
        status = BLOCKED_STATUS
        reason = "source_stability_window_not_ready"
    elif previous_source is None:
        status = SAMPLE_STATUS
        reason = "recorded_first_source_stability_sample"
    elif blockers:
        status = BLOCKED_STATUS
        reason = "source_stability_window_not_ready"
    else:
        status = READY_STATUS
        reason = "source_stability_window_ready"

    ready = status == READY_STATUS
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _iso(now),
        "active_blocker_id": blocker_id,
        "status": status,
        "reason": reason,
        "boundary": BOUNDARY,
        "source_state": current_source_state,
        "previous_source_state": previous_summary,
        "min_quiet_seconds": int(min_quiet_seconds),
        "quiet_elapsed_seconds": quiet_elapsed_seconds,
        "required_source_head": required_source_head,
        "required_origin_main": required_origin_main,
        "blockers": blockers,
        "answers": {
            "source_stability_window_ready": ready,
            "approval_granted_by_this_packet": False,
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
            "cost_gate_lowering_performed": False,
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "promotion_proof": False,
            "profit_proof": False,
        },
        "max_safe_next_action": (
            "REGENERATE_CURRENT_HEAD_E3_BB_REQUEST"
            if ready
            else (
                "RECHECK_SOURCE_AFTER_QUIET_WINDOW_NO_RUNTIME_ACTION"
                if status == SAMPLE_STATUS
                else "RESOLVE_SOURCE_BLOCKERS_NO_RUNTIME_ACTION"
            )
        ),
    }


def render_markdown(packet: dict[str, Any]) -> str:
    source = packet.get("source_state") or {}
    return "\n".join(
        [
            "# Source Stability Window Guard",
            "",
            f"- Status: `{packet.get('status')}`",
            f"- Active blocker: `{packet.get('active_blocker_id')}`",
            f"- Source head: `{source.get('head')}`",
            f"- Origin main: `{source.get('origin_main')}`",
            f"- Worktree clean: `{source.get('worktree_clean')}`",
            f"- Min quiet seconds: `{packet.get('min_quiet_seconds')}`",
            f"- Quiet elapsed seconds: `{packet.get('quiet_elapsed_seconds')}`",
            f"- Blockers: `{packet.get('blockers')}`",
            "",
            packet.get("boundary") or "",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a source-stability window guard artifact."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--previous-json", type=Path)
    parser.add_argument("--min-quiet-seconds", type=int, default=60)
    parser.add_argument("--required-source-head")
    parser.add_argument("--required-origin-main")
    parser.add_argument(
        "--active-blocker-id",
        default=ACTIVE_BLOCKER_ID,
        help=(
            "TODO blocker id to bind into the guard artifact; defaults to the "
            "historical order-capable fresh-window gate for compatibility."
        ),
    )
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
    previous = _read_json(args.previous_json)
    source_state = collect_source_state(args.repo_root.resolve(), now_utc=now)
    packet = build_source_stability_window_guard(
        current_source_state=source_state,
        previous_guard=previous,
        min_quiet_seconds=args.min_quiet_seconds,
        required_source_head=args.required_source_head,
        required_origin_main=args.required_origin_main,
        active_blocker_id=args.active_blocker_id,
        now_utc=now,
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
