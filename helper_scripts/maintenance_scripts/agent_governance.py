#!/usr/bin/env python3
"""Public facade for the Development-Agent Governance Module.

The stable API stays here; Registry, Dispatch/Context, Closure/Authority,
Evidence Reuse, and
permission policy live in cohesive internal Implementation files so reviewers
can load only the Interface they need.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


IMPLEMENTATION_DIR = Path(__file__).resolve().parent
if str(IMPLEMENTATION_DIR) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_DIR))

from agent_governance_closure import (  # noqa: E402
    validate_closure,
)
from agent_governance_closure_quality import (  # noqa: E402
    build_scheduled_closure_quality_followup,
    closure_quality_followup_digest,
    summarize_closure_quality_followups,
    validate_closure_quality_followup,
)
from agent_governance_capture import (  # noqa: E402
    LOCAL_REPRODUCIBLE,
    ORCHESTRATOR_BOUND,
    PLATFORM_OR_EXTERNAL_ATTESTED,
    TRUST_TIERS,
    build_unsigned_telemetry_record,
    capture_command,
    capture_repository,
    validate_command_capture,
    validate_repository_capture,
    validate_telemetry_record,
)
from agent_governance_command_capture_v2 import (  # noqa: E402
    capture_governed_command,
    validate_governed_command_capture,
)
from agent_governance_projection import project_closure  # noqa: E402
from agent_governance_authority import (  # noqa: E402
    authority_claim_digest,
    build_authority_claim,
    resolve_authority_claims,
)
from agent_governance_effects import build_ops_evidence  # noqa: E402
from agent_governance_external_evidence import (  # noqa: E402
    validate_external_evidence_capture,
)
from agent_governance_evidence import (  # noqa: E402
    assess_test_evidence_reuse,
    build_test_execution_receipt,
    build_test_recheck_receipt,
    test_evidence_signature,
    validate_test_evidence_reuse_receipt,
    validate_test_execution_receipt,
)
from agent_governance_execution import (  # noqa: E402
    capture_repository_baseline,
    compile_context,
    context_plan_digest,
    materialize_context_artifact,
    route_task,
    task_contract_digest,
    validate_context_artifact,
)
from agent_governance_execution_dag import (  # noqa: E402
    delegated_execution_projection,
    execution_dag_digest,
    non_call_controller_node_ids,
    topological_waves,
)
from agent_governance_permissions import (  # noqa: E402
    authorize_command,
    authorize_native_command,
)
from agent_governance_observations import (  # noqa: E402
    build_business_outcome_receipt,
    build_runtime_observation_receipt,
    build_source_change_receipt,
    build_source_review_receipt,
    validate_observation_evidence,
)
from agent_governance_registry import (  # noqa: E402
    load_registry,
    native_agent_binding,
    native_agent_contract,
    render_all,
    render_views,
    validate_registry,
)
from agent_governance_repository_changes import (  # noqa: E402
    capture_repository_change,
    validate_repository_change_record,
)
from agent_governance_workflow_receipts import (  # noqa: E402
    build_controller_workflow_call_record,
    build_workflow_call_manifest,
    build_workflow_wave_record,
    canonical_digest,
    validate_role_fragment_producer,
    validate_workflow_call_manifest,
    validate_workflow_call_record,
    validate_workflow_wave_record,
)
from agent_governance_task_control import (  # noqa: E402
    adjudicate_continuation,
    filesystem_writer_lease_action,
    is_dispatchable,
    next_action_may_be_null,
    progress_snapshot,
    queue_lane,
)


__all__ = [
    "assess_test_evidence_reuse",
    "adjudicate_continuation",
    "authority_claim_digest",
    "authorize_command",
    "authorize_native_command",
    "build_authority_claim",
    "build_business_outcome_receipt",
    "build_controller_workflow_call_record",
    "build_ops_evidence",
    "build_scheduled_closure_quality_followup",
    "build_runtime_observation_receipt",
    "build_source_change_receipt",
    "build_source_review_receipt",
    "build_test_execution_receipt",
    "build_test_recheck_receipt",
    "build_unsigned_telemetry_record",
    "build_workflow_call_manifest",
    "build_workflow_wave_record",
    "canonical_digest",
    "capture_command",
    "capture_governed_command",
    "capture_repository",
    "capture_repository_change",
    "capture_repository_baseline",
    "checkpoint_chain_id",
    "compile_context",
    "closure_quality_followup_digest",
    "context_plan_digest",
    "delegated_execution_projection",
    "execution_dag_digest",
    "filesystem_writer_lease_action",
    "is_dispatchable",
    "materialize_context_artifact",
    "native_agent_binding",
    "native_agent_contract",
    "next_action_may_be_null",
    "load_registry",
    "project_closure",
    "progress_snapshot",
    "queue_lane",
    "render_all",
    "render_views",
    "resolve_authority_claims",
    "non_call_controller_node_ids",
    "route_task",
    "summarize_closure_quality_followups",
    "test_evidence_signature",
    "task_contract_digest",
    "topological_waves",
    "LOCAL_REPRODUCIBLE",
    "ORCHESTRATOR_BOUND",
    "PLATFORM_OR_EXTERNAL_ATTESTED",
    "TRUST_TIERS",
    "validate_closure",
    "validate_closure_quality_followup",
    "validate_command_capture",
    "validate_governed_command_capture",
    "validate_context_artifact",
    "validate_external_evidence_capture",
    "validate_observation_evidence",
    "validate_repository_capture",
    "validate_repository_change_record",
    "validate_role_fragment_producer",
    "validate_telemetry_record",
    "validate_test_evidence_reuse_receipt",
    "validate_test_execution_receipt",
    "validate_registry",
    "validate_workflow_call_manifest",
    "validate_workflow_call_record",
    "validate_workflow_wave_record",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("validate", help="validate the canonical registry")
    render = subparsers.add_parser("render", help="render platform/profile Adapter views")
    render.add_argument("--check", action="store_true", help="report drift without writing")
    route = subparsers.add_parser("route", help="compile JSON task facts into a hybrid DAG")
    route.add_argument("task_facts", help="JSON object or @path-to-JSON")
    continuation = subparsers.add_parser(
        "continuation", help="adjudicate one finite or explicit operator-loop boundary"
    )
    continuation.add_argument(
        "bundle", help="JSON {continuation_mode,current,previous?} or @path"
    )
    writer_lease = subparsers.add_parser(
        "writer-lease", help="acquire, inspect, renew, or release a linked-worktree writer lease"
    )
    writer_lease.add_argument(
        "--lease-action", choices=("acquire", "status", "renew", "release"), required=True
    )
    writer_lease.add_argument("--repo", type=Path, default=Path("."))
    writer_lease.add_argument("--task-id", required=True)
    writer_lease.add_argument("--owner", required=True)
    writer_lease.add_argument("--lease-id")
    writer_lease.add_argument("--ttl-seconds", type=int, default=7200)
    context = subparsers.add_parser("context", help="compile a lossless adaptive context plan")
    context.add_argument("--role", required=True)
    context.add_argument("task_facts", help="JSON object or @path-to-JSON")
    closure = subparsers.add_parser("closure", help="validate closure_packet_v1 JSON")
    closure.add_argument("packet", help="JSON object or @path-to-JSON")
    quality = subparsers.add_parser(
        "closure-quality",
        help="validate externally attested closure_quality_followup_v1 JSON",
    )
    quality.add_argument("bundle", help="JSON {followup, closure, attestation_index?} or @path")
    projection = subparsers.add_parser("project-closure", help="render one validated closure to Markdown")
    projection.add_argument("packet", help="JSON object or @path-to-JSON")
    authority = subparsers.add_parser("authority", help="resolve typed authority claims")
    authority.add_argument("claims", help="JSON array or @path-to-JSON")
    evidence_key = subparsers.add_parser("evidence-key", help="hash exact test evidence facts")
    evidence_key.add_argument("facts", help="JSON object or @path-to-JSON")
    authorize = subparsers.add_parser("authorize-command", help="preflight Bash for a governed identity")
    identity = authorize.add_mutually_exclusive_group(required=True)
    identity.add_argument("--role")
    identity.add_argument("--native-agent")
    authorize.add_argument("--command", dest="shell_command", required=True)
    capture = subparsers.add_parser(
        "capture-command", help="execute one Context-bound local argv and emit command_capture_v2",
    )
    capture.add_argument("--native-agent", required=True)
    capture.add_argument("--node-id", required=True)
    capture.add_argument("--context-artifact", required=True)
    capture.add_argument("--timeout-seconds", type=int, default=120)
    capture.add_argument("command_argv", nargs=argparse.REMAINDER)
    return parser


def _json_arg(value: str):
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(raw_argv)
    registry = load_registry()
    errors = validate_registry(registry)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    if args.action == "validate":
        print(json.dumps({"status": "PASS", "roles": len(registry["roles"])}, ensure_ascii=False))
        return 0
    if args.action == "route":
        print(json.dumps(route_task(_json_arg(args.task_facts)), ensure_ascii=False, indent=2))
        return 0
    if args.action == "continuation":
        bundle = _json_arg(args.bundle)
        try:
            packet = adjudicate_continuation(
                continuation_mode=bundle["continuation_mode"],
                current=bundle["current"],
                previous=bundle.get("previous"),
            )
        except (KeyError, TypeError, ValueError) as error:
            print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
            return 2
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.action == "writer-lease":
        try:
            packet = filesystem_writer_lease_action(
                action=args.lease_action,
                repo=args.repo,
                task_id=args.task_id,
                owner=args.owner,
                lease_id=args.lease_id,
                ttl_seconds=args.ttl_seconds,
            )
        except (OSError, TypeError, ValueError) as error:
            print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
            return 2
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if packet["status"] == "PASS" else 3
    if args.action == "context":
        print(json.dumps(compile_context(args.role, _json_arg(args.task_facts), registry), ensure_ascii=False, indent=2))
        return 0
    if args.action == "closure":
        errors = validate_closure(_json_arg(args.packet))
        print(json.dumps({"status": "FAIL" if errors else "PASS", "errors": errors}, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    if args.action == "closure-quality":
        bundle = _json_arg(args.bundle)
        if not isinstance(bundle, dict):
            quality_errors = ["closure-quality bundle must be an object"]
        else:
            quality_errors = validate_closure_quality_followup(
                bundle.get("followup"),
                bundle.get("closure"),
                attestation_index=bundle.get("attestation_index"),
            )
        print(
            json.dumps(
                {
                    "status": "FAIL" if quality_errors else "PASS",
                    "errors": quality_errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if quality_errors else 0
    if args.action == "project-closure":
        try:
            print(project_closure(_json_arg(args.packet)), end="")
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        return 0
    if args.action == "authority":
        print(json.dumps(resolve_authority_claims(_json_arg(args.claims)), ensure_ascii=False, indent=2))
        return 0
    if args.action == "evidence-key":
        print(test_evidence_signature(_json_arg(args.facts)))
        return 0
    if args.action == "authorize-command":
        decision = (
            authorize_native_command(args.native_agent, args.shell_command, registry)
            if args.native_agent is not None
            else authorize_command(args.role, args.shell_command, registry)
        )
        print(json.dumps(decision, ensure_ascii=False))
        return 0 if decision["allowed"] else 2
    if args.action == "capture-command":
        if "--" not in raw_argv:
            print(json.dumps({
                "status": "DENIED",
                "error": "capture-command argv must appear only after --",
            }, ensure_ascii=False))
            return 2
        command_argv = raw_argv[raw_argv.index("--") + 1:]
        if not command_argv:
            print(json.dumps({"status": "DENIED", "error": "command argv is empty"}))
            return 2
        try:
            record = capture_governed_command(
                native_agent=args.native_agent, node_id=args.node_id,
                context_artifact=_json_arg(args.context_artifact), argv=command_argv,
                root=Path.cwd(), timeout_seconds=args.timeout_seconds,
            )
        except (OSError, PermissionError, RuntimeError, TypeError, ValueError) as error:
            print(json.dumps({"status": "DENIED", "error": str(error)}, ensure_ascii=False))
            return 2
        print(json.dumps(record, ensure_ascii=False, sort_keys=True))
        return 0
    if args.action != "render":
        print(f"unsupported action: {args.action}", file=sys.stderr)
        return 2
    drift = render_all(registry, check=args.check)
    if args.check and drift:
        print(json.dumps({"status": "DRIFT", "paths": drift}, ensure_ascii=False))
        return 1
    if not args.check:
        residual = render_all(registry, check=True)
        if residual:
            print(json.dumps({"status": "DRIFT", "updated": drift, "residual_paths": residual}, ensure_ascii=False))
            return 1
    print(json.dumps({"status": "PASS", "updated": drift}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
