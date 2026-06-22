#!/usr/bin/env python3
"""Machine-readable dry-run review for the demo-learning cron stack.

This artifact captures the operator dry-run preview requested by the activation
packet. It never sets the apply gate and never mutates crontab.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from demo_learning_stack_activation_packet import build_activation_packet

SCHEMA_VERSION = "demo_learning_stack_dry_run_review_v1"
DEFAULT_TIMEOUT_SECONDS = 120
MAX_CAPTURE_CHARS = 12000


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _tail(value: str, limit: int = MAX_CAPTURE_CHARS) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _git_head(repo_root: Path) -> tuple[str | None, str | None]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"git_head_error:{type(exc).__name__}"
    if proc.returncode != 0:
        return None, _tail((proc.stderr or proc.stdout or "git_head_failed").strip(), 512)
    return proc.stdout.strip(), None


def _command_shell(command: dict[str, Any] | None) -> str | None:
    if isinstance(command, dict):
        shell = command.get("shell")
        return str(shell) if shell else None
    return None


def _skip_status(packet_status: str) -> str:
    if packet_status == "SOURCE_NOT_READY":
        return "DRY_RUN_SKIPPED_ACTIVATION_SOURCE_NOT_READY"
    if packet_status == "STACK_ALREADY_ACTIVE":
        return "DRY_RUN_SKIPPED_STACK_ALREADY_ACTIVE"
    return "DRY_RUN_SKIPPED_ACTIVATION_NOT_READY"


def _base_payload(
    *,
    data_dir: Path,
    repo_root: Path,
    expected_head: str | None,
    now: dt.datetime,
    activation_packet: dict[str, Any],
) -> dict[str, Any]:
    commands = (
        activation_packet.get("operator_commands")
        if isinstance(activation_packet.get("operator_commands"), dict)
        else {}
    )
    answers = (
        activation_packet.get("answers")
        if isinstance(activation_packet.get("answers"), dict)
        else {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "data_dir": str(data_dir),
        "repo_root": str(repo_root),
        "expected_head": expected_head,
        "activation_packet_status": activation_packet.get("status"),
        "activation_packet_reason": activation_packet.get("reason"),
        "activation_packet_install_review_ready": activation_packet.get(
            "install_review_ready"
        ),
        "activation_packet_missing_cron_count": answers.get("missing_cron_count"),
        "dry_run_preview_shell": _command_shell(commands.get("dry_run_preview")),
        "operator_only_apply_shell": _command_shell(commands.get("operator_only_apply")),
        "operator_only_rollback_shell": _command_shell(
            commands.get("operator_only_rollback")
        ),
        "answers": {
            "dry_run_preview_executed": False,
            "dry_run_preview_passed": False,
            "crontab_mutated": False,
            "operator_apply_required": False,
            "global_cost_gate_lowering_recommended": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_proof": False,
        },
        "boundary": (
            "dry-run review artifact only; OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY "
            "is forced to 0; no crontab mutation, source sync, deploy, restart, "
            "PG write/schema migration, Bybit private/signed/trading call, order "
            "authority, probe authority, writer enablement, main Cost Gate lowering, "
            "or promotion proof"
        ),
    }


def build_dry_run_review(
    *,
    data_dir: Path,
    repo_root: Path,
    expected_head: str | None,
    python_bin: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    resolved_head = expected_head
    head_error: str | None = None
    if not resolved_head:
        resolved_head, head_error = _git_head(repo_root)

    if head_error:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
            "data_dir": str(data_dir),
            "repo_root": str(repo_root),
            "expected_head": resolved_head,
            "status": "DRY_RUN_SKIPPED_SOURCE_HEAD_UNAVAILABLE",
            "reason": head_error,
            "operator_next_action": "repair_runtime_source_before_dry_run_preview",
            "answers": {
                "dry_run_preview_executed": False,
                "dry_run_preview_passed": False,
                "crontab_mutated": False,
                "operator_apply_required": False,
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
                "probe_authority_granted": False,
                "promotion_proof": False,
            },
            "boundary": (
                "dry-run review artifact only; no crontab mutation or trading authority"
            ),
        }
        return payload

    activation_packet = build_activation_packet(
        data_dir=data_dir,
        repo_root=repo_root,
        expected_head=resolved_head,
        crontab_text_file=None,
        max_heartbeat_age_minutes=90,
        max_status_age_minutes=180,
        python_bin=python_bin,
        now_utc=now,
    )
    payload = _base_payload(
        data_dir=data_dir,
        repo_root=repo_root,
        expected_head=resolved_head,
        now=now,
        activation_packet=activation_packet,
    )
    packet_status = str(activation_packet.get("status") or "UNKNOWN")
    if packet_status != "READY_FOR_OPERATOR_DRY_RUN":
        payload.update({
            "status": _skip_status(packet_status),
            "reason": f"activation_packet_status:{packet_status}",
            "operator_next_action": activation_packet.get("operator_next_action")
            or "refresh_activation_packet_before_dry_run_preview",
            "dry_run_preview": {
                "executed": False,
                "returncode": None,
                "stdout_tail": "",
                "stderr_tail": "",
            },
        })
        return payload

    installer = repo_root / "helper_scripts" / "cron" / "install_demo_learning_stack_crons.sh"
    env = os.environ.copy()
    env.update({
        "OPENCLAW_BASE_DIR": str(repo_root),
        "OPENCLAW_DATA_DIR": str(data_dir),
        "OPENCLAW_PYTHON_BIN": python_bin,
        "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY": "0",
        "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD": str(resolved_head),
        "OPENCLAW_EXPECTED_SOURCE_HEAD": str(resolved_head),
        "OPENCLAW_DEMO_LEARNING_STACK_PREFLIGHT": "1",
        "OPENCLAW_DEMO_LEARNING_STACK_PREINSTALL_REFRESH": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    try:
        proc = subprocess.run(
            [str(installer)],
            capture_output=True,
            check=False,
            env=env,
            text=True,
            timeout=timeout_seconds,
        )
        rc = int(proc.returncode)
        stdout_tail = _tail(proc.stdout or "")
        stderr_tail = _tail(proc.stderr or "")
        run_error = None
    except subprocess.TimeoutExpired as exc:
        rc = 124
        stdout_tail = _tail(exc.stdout or "" if isinstance(exc.stdout, str) else "")
        stderr_tail = _tail(exc.stderr or "" if isinstance(exc.stderr, str) else "")
        run_error = f"timeout_after_{timeout_seconds}s"
    except OSError as exc:
        rc = 127
        stdout_tail = ""
        stderr_tail = f"{type(exc).__name__}: {exc}"
        run_error = f"exec_error:{type(exc).__name__}"

    passed = rc == 0 and run_error is None
    payload["answers"].update({
        "dry_run_preview_executed": True,
        "dry_run_preview_passed": passed,
        "operator_apply_required": passed,
    })
    payload.update({
        "status": (
            "DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED"
            if passed
            else "DRY_RUN_PREVIEW_FAILED_REPAIR_REQUIRED"
        ),
        "reason": (
            "installer_dry_run_preview_passed_without_crontab_mutation"
            if passed
            else "installer_dry_run_preview_failed"
        ),
        "operator_next_action": (
            "operator_review_dry_run_preview_then_apply_learning_stack_if_accepted"
            if passed
            else "repair_demo_learning_stack_installer_before_operator_apply"
        ),
        "dry_run_preview": {
            "executed": True,
            "returncode": rc,
            "run_error": run_error,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "forced_apply_gate": "0",
            "preinstall_refresh": "0",
            "mutates_crontab": False,
        },
    })
    return payload


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/tmp/openclaw"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--expected-head", default=None)
    parser.add_argument("--python-bin", default="python3")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--now-utc", default=None)
    parser.add_argument("--json-output", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.timeout_seconds <= 0:
        raise SystemExit("timeout must be positive")
    now = _parse_ts(args.now_utc) if args.now_utc else None
    payload = build_dry_run_review(
        data_dir=args.data_dir,
        repo_root=args.repo_root,
        expected_head=args.expected_head,
        python_bin=args.python_bin,
        timeout_seconds=args.timeout_seconds,
        now_utc=now,
    )
    if args.json_output is not None:
        _write_json_atomic(args.json_output, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
