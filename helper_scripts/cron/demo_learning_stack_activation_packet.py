#!/usr/bin/env python3
"""Read-only activation packet for the demo-learning cron stack.

The packet turns the stack healthcheck plus Cost Gate learning-lane preflight
into one operator-review artifact. It does not install cron entries and does
not grant probe/order authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from demo_learning_stack_healthcheck import build_healthcheck

HELPER_DIR = Path(__file__).resolve().parents[1]
RESEARCH_DIR = HELPER_DIR / "research"
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

from cost_gate_learning_lane.status import (  # noqa: E402
    build_cost_gate_learning_lane_activation_preflight,
)

SCHEMA_VERSION = "demo_learning_stack_activation_packet_v1"

STACK_CRONS = (
    {
        "id": "demo_learning_evidence",
        "marker": "demo_learning_evidence_audit_cron.sh",
        "default_schedule": "7,37 * * * *",
        "purpose": "record whether demo/live_demo rejects are present and classified",
        "heartbeat": "cron_heartbeat/demo_learning_evidence_audit.last_fire",
        "status_log": "logs/demo_learning_evidence_audit.log",
    },
    {
        "id": "sealed_horizon_probe_preflight",
        "marker": "sealed_horizon_probe_preflight_cron.sh",
        "default_schedule": "22 * * * *",
        "purpose": "refresh sealed bounded-probe preflight before review artifacts",
        "heartbeat": "cron_heartbeat/sealed_horizon_probe_preflight.last_fire",
        "status_log": "logs/sealed_horizon_probe_preflight.log",
    },
    {
        "id": "cost_gate_learning_lane",
        "marker": "cost_gate_learning_lane_cron.sh",
        "default_schedule": "27 * * * *",
        "purpose": "materialize Cost Gate rejects, refresh outcomes, and review blocked edge",
        "heartbeat": "cron_heartbeat/cost_gate_learning_lane.last_fire",
        "status_log": "logs/cost_gate_learning_lane.log",
    },
    {
        "id": "demo_learning_stack_healthcheck",
        "marker": "demo_learning_stack_healthcheck_cron.sh",
        "default_schedule": "32 * * * *",
        "purpose": "publish machine-readable stack health for alpha/worklist consumers",
        "heartbeat": "cron_heartbeat/demo_learning_stack_healthcheck.last_fire",
        "status_log": "logs/demo_learning_stack_healthcheck.log",
    },
)


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


def _quote_env_command(env: dict[str, str], argv: list[str]) -> str:
    parts = [f"{key}={shlex.quote(value)}" for key, value in env.items()]
    parts.extend(shlex.quote(part) for part in argv)
    return " ".join(parts)


def _build_commands(
    *,
    repo_root: Path,
    data_dir: Path,
    expected_head: str | None,
    python_bin: str,
) -> dict[str, Any]:
    installer = (
        repo_root / "helper_scripts" / "cron" / "install_demo_learning_stack_crons.sh"
    )
    healthcheck = (
        repo_root / "helper_scripts" / "cron" / "demo_learning_stack_healthcheck.py"
    )
    env = {
        "OPENCLAW_BASE_DIR": str(repo_root),
        "OPENCLAW_DATA_DIR": str(data_dir),
    }
    if expected_head:
        env["OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD"] = expected_head
        env["OPENCLAW_EXPECTED_SOURCE_HEAD"] = expected_head

    dry_run_env = {**env, "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY": "0"}
    apply_env = {**env, "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY": "1"}
    verify_args = [
        python_bin,
        str(healthcheck),
        "--data-dir",
        str(data_dir),
        "--repo-root",
        str(repo_root),
        "--fail-on-not-active",
    ]
    if expected_head:
        verify_args.extend(["--expected-head", expected_head])
    return {
        "dry_run_preview": {
            "argv": [str(installer)],
            "env": dry_run_env,
            "shell": _quote_env_command(dry_run_env, [str(installer)]),
            "mutates_crontab": False,
        },
        "operator_only_apply": {
            "argv": [str(installer)],
            "env": apply_env,
            "shell": _quote_env_command(apply_env, [str(installer)]),
            "mutates_crontab": True,
            "requires_operator_approval": True,
        },
        "operator_only_rollback": {
            "argv": [str(installer), "--remove"],
            "env": apply_env,
            "shell": _quote_env_command(apply_env, [str(installer), "--remove"]),
            "mutates_crontab": True,
            "requires_operator_approval": True,
        },
        "post_install_verification": {
            "argv": verify_args,
            "shell": " ".join(shlex.quote(part) for part in verify_args),
            "when": "after first scheduled stack cycle, normally within 90 minutes",
            "mutates_crontab": False,
        },
    }


def _missing_crons(healthcheck: dict[str, Any]) -> list[str]:
    answers = healthcheck.get("answers") or {}
    checks = {
        "demo_learning_evidence": "demo_learning_evidence_cron_entry_present",
        "sealed_horizon_probe_preflight": (
            "sealed_horizon_probe_preflight_cron_entry_present"
        ),
        "cost_gate_learning_lane": "cost_gate_learning_lane_cron_entry_present",
        "demo_learning_stack_healthcheck": (
            "demo_learning_stack_healthcheck_cron_entry_present"
        ),
    }
    return [name for name, key in checks.items() if answers.get(key) is not True]


def _next_action_links(healthcheck: dict[str, Any]) -> list[str]:
    next_action = healthcheck.get("next_action")
    return [str(next_action)] if next_action else []


def _decide_status(
    *,
    healthcheck: dict[str, Any],
    activation_preflight: dict[str, Any],
) -> dict[str, Any]:
    health_answers = healthcheck.get("answers") or {}
    activation_answers = activation_preflight.get("answers") or {}
    missing = _missing_crons(healthcheck)
    health_status = str(healthcheck.get("status") or "UNKNOWN")
    activation_blockers = list(activation_preflight.get("activation_blockers") or [])
    source_ready = health_answers.get("source_ready") is True
    activation_source_ready = (
        activation_answers.get("runtime_source_ready_for_activation") is True
    )

    if not source_ready or not activation_source_ready:
        return {
            "status": "SOURCE_NOT_READY",
            "reason": "runtime_source_not_clean_synced_or_activation_ready",
            "operator_next_action": "reconcile_source_before_any_stack_install",
            "missing_links": [
                "runtime_source_clean_expected_head",
                *activation_blockers,
            ],
            "install_review_ready": False,
        }
    if health_status == "EVIDENCE_STACK_ACTIVE":
        return {
            "status": "STACK_ALREADY_ACTIVE",
            "reason": "demo_learning_stack_healthcheck_is_active",
            "operator_next_action": "observe_blocked_outcome_review_and_bounded_probe_reviews",
            "missing_links": [],
            "install_review_ready": False,
        }
    if missing:
        return {
            "status": "READY_FOR_OPERATOR_DRY_RUN",
            "reason": "source_ready_but_one_or_more_stack_crons_missing",
            "operator_next_action": (
                "run_dry_run_preview_then_apply_only_if_installer_preflight_passes"
            ),
            "missing_links": [f"cron:{name}" for name in missing],
            "install_review_ready": True,
        }
    if health_status in {
        "INSTALLED_NOT_FIRING",
        "FIRING_NO_RECENT_STATUS",
        "ERROR",
        "FIRING_BUT_ARTIFACTS_INCOMPLETE",
    }:
        return {
            "status": "STACK_INSTALLED_REPAIR_REQUIRED",
            "reason": str(healthcheck.get("reason") or "installed_stack_not_healthy"),
            "operator_next_action": str(
                healthcheck.get("next_action") or "inspect_stack_logs"
            ),
            "missing_links": _next_action_links(healthcheck),
            "install_review_ready": False,
        }
    if health_status in {
        "RUNNING_NO_LEDGER_ROWS",
        "LEDGER_ONLY_NEEDS_OUTCOME_REFRESH",
        "BOUNDED_PROBE_PREFLIGHT_MISSING",
        "BOUNDED_PROBE_REVIEW_ARTIFACTS_MISSING",
    }:
        return {
            "status": "LEARNING_REVIEW_REFRESH_REQUIRED",
            "reason": str(healthcheck.get("reason") or "learning_artifacts_not_complete"),
            "operator_next_action": str(
                healthcheck.get("next_action") or "refresh_learning_review_artifacts"
            ),
            "missing_links": _next_action_links(healthcheck),
            "install_review_ready": False,
        }
    return {
        "status": "REVIEW_REQUIRED",
        "reason": f"unclassified_health_status:{health_status}",
        "operator_next_action": str(healthcheck.get("next_action") or "manual_review"),
        "missing_links": _next_action_links(healthcheck),
        "install_review_ready": False,
    }


def build_activation_packet(
    *,
    data_dir: Path,
    repo_root: Path,
    expected_head: str | None,
    crontab_text_file: Path | None,
    max_heartbeat_age_minutes: int,
    max_status_age_minutes: int,
    python_bin: str,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    healthcheck = build_healthcheck(
        data_dir=data_dir,
        repo_root=repo_root,
        expected_head=expected_head,
        crontab_text_file=crontab_text_file,
        max_heartbeat_age_minutes=max_heartbeat_age_minutes,
        max_status_age_minutes=max_status_age_minutes,
        now_utc=now,
    )
    activation_preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo_root,
        expected_head=expected_head,
        now_utc=now,
    )
    decision = _decide_status(
        healthcheck=healthcheck,
        activation_preflight=activation_preflight,
    )
    missing = _missing_crons(healthcheck)
    commands = _build_commands(
        repo_root=repo_root,
        data_dir=data_dir,
        expected_head=expected_head,
        python_bin=python_bin,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "data_dir": str(data_dir),
        "repo_root": str(repo_root),
        "expected_head": expected_head,
        **decision,
        "answers": {
            "source_ready": (healthcheck.get("answers") or {}).get("source_ready"),
            "stack_installed": (healthcheck.get("answers") or {}).get(
                "stack_installed"
            ),
            "missing_cron_count": len(missing),
            "missing_crons": missing,
            "sealed_horizon_probe_preflight_present": (
                (healthcheck.get("answers") or {}).get(
                    "sealed_horizon_probe_preflight_present"
                )
            ),
            "bounded_probe_reviews_present": (healthcheck.get("answers") or {}).get(
                "bounded_probe_reviews_present"
            ),
            "cost_gate_activation_ready": (
                (activation_preflight.get("answers") or {}).get("activation_ready")
            ),
            "runtime_writer_enabled": (
                (activation_preflight.get("answers") or {}).get(
                    "runtime_writer_enabled"
                )
            ),
            "global_cost_gate_lowering_recommended": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_proof": False,
        },
        "planned_stack": {
            "cron_count": len(STACK_CRONS),
            "crons": list(STACK_CRONS),
            "healthcheck_status": healthcheck.get("status"),
            "cost_gate_activation_status": activation_preflight.get("status"),
        },
        "profitability_path": {
            "cost_gate_escape_thesis": (
                "collect rejected demo signals, score matched side-cell/horizon "
                "blocked outcomes, review bounded demo probes only when matched "
                "controls and execution-realism gates are present"
            ),
            "edge_amplification_levers": [
                "side_cell_filtering",
                "horizon_retiming",
                "low_friction_execution_filtering",
                "matched_control_blocked_signal_review",
                "bounded_demo_probe_execution_realism_repair",
            ],
            "next_profit_gate_after_activation": (
                "bounded_probe_result_review_and_execution_realism_review_with_matched_controls"
            ),
        },
        "operator_commands": commands,
        "healthcheck": healthcheck,
        "cost_gate_activation_preflight": activation_preflight,
        "boundary": (
            "read-only activation packet only; no crontab mutation, source sync, "
            "deploy, restart, PG write/schema migration, Bybit private/signed/"
            "trading call, order authority, probe authority, writer enablement, "
            "main Cost Gate lowering, or promotion proof"
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/tmp/openclaw"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--expected-head", default=None)
    parser.add_argument("--crontab-text-file", type=Path, default=None)
    parser.add_argument("--max-heartbeat-age-minutes", type=int, default=90)
    parser.add_argument("--max-status-age-minutes", type=int, default=180)
    parser.add_argument("--python-bin", default="python3")
    parser.add_argument("--now-utc", default=None)
    parser.add_argument("--json-output", type=Path, default=None)
    return parser.parse_args(argv)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.max_heartbeat_age_minutes <= 0 or args.max_status_age_minutes <= 0:
        raise SystemExit("age thresholds must be positive")
    now = _parse_ts(args.now_utc) if args.now_utc else None
    payload = build_activation_packet(
        data_dir=args.data_dir,
        repo_root=args.repo_root,
        expected_head=args.expected_head,
        crontab_text_file=args.crontab_text_file,
        max_heartbeat_age_minutes=args.max_heartbeat_age_minutes,
        max_status_age_minutes=args.max_status_age_minutes,
        python_bin=args.python_bin,
        now_utc=now,
    )
    if args.json_output is not None:
        _write_json_atomic(args.json_output, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
