#!/usr/bin/env python3
"""Fail-closed deployment intent Adapter for the existing atomic build/restart component.

This script never infers approval from a clean checkout or a PM statement.  It
binds an immutable intent digest, source HEAD, clean tree, host, expiry, typed
confirmation, and the exact component script bytes before any effect.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_DIR = Path(__file__).resolve().parent
if str(IMPLEMENTATION_DIR) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_DIR))

from agent_governance_effects import (  # noqa: E402
    build_effect_evidence,
    build_effect_receipt,
    build_ops_evidence,
    build_runtime_environment_attestation,
    effect_receipt_digest,
    runtime_attestation_digest,
    runtime_environment_identity_digest,
    validate_effect_receipt,
    validate_runtime_attestation_for_intent,
    validate_runtime_environment_attestation,
)
from agent_governance_schema import schema_subset_errors  # noqa: E402


DEPLOY_COMPONENT = REPO_ROOT / "helper_scripts/build_then_restart_atomic.sh"
INTENT_SCHEMA_PATH = REPO_ROOT / ".codex/schemas/deployment_intent_v1.schema.json"
REQUIRED_HARD_STOPS = {
    "no live/mainnet authority expansion",
    "no risk/cost-gate/decision-lease bypass",
}


@lru_cache(maxsize=1)
def _intent_schema() -> dict[str, Any]:
    return json.loads(INTENT_SCHEMA_PATH.read_text(encoding="utf-8"))


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


def expected_confirmation(intent: dict[str, Any]) -> str:
    return (
        f"deploy:{intent.get('target_host', '')}:{intent.get('expected_source_head', '')}:"
        f"{intent.get('intent_id', '')}"
    )


def validate_intent(
    intent: Any,
    *,
    supplied_intent_digest: str,
    actual_intent_digest: str,
    actual_source_head: str,
    tree_clean: bool,
    actual_host: str,
    deploy_script_digest: str,
    now: str,
) -> list[str]:
    schema = _intent_schema()
    errors = [
        f"deployment intent schema violation: {error}"
        for error in schema_subset_errors(intent, schema, schema)
    ]
    if not isinstance(intent, dict):
        return errors
    required = {
        "schema_version", "intent_id", "target_host", "target_environment",
        "expected_source_head", "expected_deploy_script_sha256",
        "expected_runtime_environment_identity_digest", "require_clean_tree",
        "approved_by", "approved_at", "expires_at", "typed_confirm", "hard_stops",
    }
    if set(intent) != required:
        errors.append(f"intent fields mismatch: missing={sorted(required - set(intent))} extra={sorted(set(intent) - required)}")
    if intent.get("schema_version") != "deployment_intent_v1":
        errors.append("schema_version must be deployment_intent_v1")
    if not isinstance(intent.get("intent_id"), str) or len(intent.get("intent_id", "")) < 8:
        errors.append("intent_id is invalid")
    if intent.get("target_environment") not in {"demo", "live_demo", "research_runtime"}:
        errors.append("target_environment is outside the non-mainnet allowlist")
    if supplied_intent_digest != actual_intent_digest:
        errors.append("supplied intent digest does not match intent bytes")
    if intent.get("expected_source_head") != actual_source_head:
        errors.append("source HEAD does not match approved intent")
    if intent.get("require_clean_tree") is not True or not tree_clean:
        errors.append("deployment requires an exactly clean worktree")
    if intent.get("target_host") != actual_host:
        errors.append("target host does not match approved intent")
    if intent.get("expected_deploy_script_sha256") != deploy_script_digest:
        errors.append("deploy component bytes do not match approved intent")
    if intent.get("typed_confirm") != expected_confirmation(intent):
        errors.append("typed_confirm does not match host/head/intent identity")
    if not isinstance(intent.get("approved_by"), str) or not intent.get("approved_by", "").strip():
        errors.append("approved_by is required")
    hard_stops = intent.get("hard_stops")
    if (
        not isinstance(hard_stops, list)
        or any(not isinstance(item, str) for item in hard_stops)
        or not REQUIRED_HARD_STOPS.issubset(set(hard_stops))
    ):
        errors.append("required hard stops are missing")
    try:
        approved = parse_time(str(intent.get("approved_at", "")))
        expiry = parse_time(str(intent.get("expires_at", "")))
        current = parse_time(now)
        if not approved <= current < expiry:
            errors.append("intent is not active at current time")
        if (expiry - approved).total_seconds() > 4 * 60 * 60:
            errors.append("deployment intent TTL exceeds four hours")
    except (TypeError, ValueError):
        errors.append("intent timestamps are invalid")
    return errors


def generated_receipt_result(receipt: Any) -> tuple[int, list[str]]:
    """Return success only for a structurally canonical apply receipt.

    A closure-grade PASS additionally needs the trusted host's out-of-band
    execution attestation; packet-local receipt bytes never provide it.
    """

    errors = validate_effect_receipt(receipt, require_success=True)
    return (3, errors) if errors else (0, [])


def probe_local_runtime_environment(
    *,
    phase: str,
    expected_host: str,
    expected_source_head: str,
    now: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Fail closed until runtime exposes a non-secret, reproducible identity probe.

    Process argv/environment and deployment intent labels are not sufficient to
    prove the selected endpoint, authorization scope, and effective mode.  The
    Adapter therefore remains non-executable instead of manufacturing those
    facts from caller input.
    """

    _ = (phase, expected_host, expected_source_head, now)
    return None, [
        "RUNTIME_ENVIRONMENT_PROBE_UNAVAILABLE: no trusted local runtime identity probe"
    ]


def reconcile_runtime_attestations(
    supplied: Any,
    probed: Any,
    intent: dict[str, Any],
    *,
    phase: str,
    now: str,
) -> list[str]:
    """Require supplied OPS evidence to match a fresh local reproduction."""

    errors = validate_runtime_attestation_for_intent(
        supplied, intent, phase=phase, now=now
    )
    errors.extend(
        validate_runtime_attestation_for_intent(
            probed, intent, phase=phase, now=now
        )
    )
    if not isinstance(supplied, dict) or not isinstance(probed, dict):
        return errors or ["runtime environment attestation is unavailable"]
    for field in (
        "host",
        "source_head",
        "config_identity_digest",
        "actual_endpoint_class",
        "allow_mainnet",
        "runtime_mode",
        "authorization_scope",
        "process_identity_digest",
        "environment_identity_digest",
    ):
        if supplied.get(field) != probed.get(field):
            errors.append(f"local runtime probe disagrees with OPS attestation: {field}")
    return errors


def git_text(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=True
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent", required=True, type=Path)
    parser.add_argument("--intent-sha256", required=True)
    parser.add_argument("--runtime-attestation", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    raw = args.intent.read_bytes()
    intent = json.loads(raw)
    errors = validate_intent(
        intent,
        supplied_intent_digest=args.intent_sha256,
        actual_intent_digest=sha256_bytes(raw),
        actual_source_head=git_text("rev-parse", "HEAD"),
        tree_clean=not bool(git_text("status", "--porcelain", "--untracked-files=all")),
        actual_host=socket.gethostname(),
        deploy_script_digest=sha256_bytes(DEPLOY_COMPONENT.read_bytes()),
        now=datetime.now().astimezone().isoformat(),
    )
    if errors:
        print(json.dumps({"status": "BLOCKED", "errors": errors}, ensure_ascii=False), file=sys.stderr)
        return 1
    if not args.apply:
        print(
            json.dumps(
                {
                    "status": "INTENT_VALIDATED_APPLY_DISABLED",
                    "intent_id": intent["intent_id"],
                    "apply_executable": False,
                    "blocked_on": "trusted local runtime identity probe",
                },
                ensure_ascii=False,
            )
        )
        return 0
    if os.environ.get("OPENCLAW_DEPLOY_ADAPTER_APPLY") != "1":
        print("apply requires OPENCLAW_DEPLOY_ADAPTER_APPLY=1", file=sys.stderr)
        return 2
    if args.runtime_attestation is None:
        print("apply requires --runtime-attestation", file=sys.stderr)
        return 4
    try:
        supplied_attestation = json.loads(
            args.runtime_attestation.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        print(f"runtime attestation is unreadable: {error}", file=sys.stderr)
        return 4
    probe_now = datetime.now().astimezone().isoformat()
    supplied_errors = validate_runtime_attestation_for_intent(
        supplied_attestation,
        intent,
        phase="preflight",
        now=probe_now,
    )
    if supplied_errors:
        print(
            json.dumps(
                {"status": "RUNTIME_ENVIRONMENT_ATTESTATION_BLOCKED", "errors": supplied_errors},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4
    probed_attestation, probe_errors = probe_local_runtime_environment(
        phase="preflight",
        expected_host=intent["target_host"],
        expected_source_head=intent["expected_source_head"],
        now=probe_now,
    )
    if probe_errors or probed_attestation is None:
        print(
            json.dumps(
                {"status": "RUNTIME_ENVIRONMENT_PROBE_UNAVAILABLE", "errors": probe_errors},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4
    reconciliation_errors = reconcile_runtime_attestations(
        supplied_attestation,
        probed_attestation,
        intent,
        phase="preflight",
        now=probe_now,
    )
    if reconciliation_errors:
        print(
            json.dumps(
                {"status": "RUNTIME_ENVIRONMENT_ATTESTATION_MISMATCH", "errors": reconciliation_errors},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4
    started_at = datetime.now().astimezone().isoformat()
    completed = subprocess.run(
        ["bash", str(DEPLOY_COMPONENT)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    completed_at = datetime.now().astimezone().isoformat()
    if completed.stdout:
        sys.stderr.buffer.write(completed.stdout)
    if completed.stderr:
        sys.stderr.buffer.write(completed.stderr)
    post_probe_now = datetime.now().astimezone().isoformat()
    post_attestation, post_probe_errors = probe_local_runtime_environment(
        phase="postcheck",
        expected_host=intent["target_host"],
        expected_source_head=intent["expected_source_head"],
        now=post_probe_now,
    )
    if post_probe_errors or post_attestation is None:
        print(
            json.dumps(
                {
                    "status": "POST_RUNTIME_ENVIRONMENT_PROBE_UNAVAILABLE",
                    "errors": post_probe_errors,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4
    post_validation_errors = validate_runtime_attestation_for_intent(
        post_attestation,
        intent,
        phase="postcheck",
        now=post_probe_now,
    )
    if post_validation_errors:
        print(
            json.dumps(
                {
                    "status": "POST_RUNTIME_ENVIRONMENT_ATTESTATION_BLOCKED",
                    "errors": post_validation_errors,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4
    receipt = build_effect_receipt(
        intent,
        intent_digest=sha256_bytes(raw),
        component_exit_code=completed.returncode,
        component_stdout=completed.stdout,
        component_stderr=completed.stderr,
        started_at=started_at,
        completed_at=completed_at,
        pre_runtime_attestation=probed_attestation,
        post_runtime_attestation=post_attestation,
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    receipt_exit, receipt_errors = generated_receipt_result(receipt)
    if receipt_errors:
        print(
            json.dumps(
                {"status": "FAILED_RECEIPT_VALIDATION", "errors": receipt_errors},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
    return receipt_exit


if __name__ == "__main__":
    raise SystemExit(main())
