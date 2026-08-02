#!/usr/bin/env python3
"""Build a non-authoritative S2E-LW1 external-prerequisite action packet."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "program_code" / "ml_training"
for candidate in (Path(__file__).resolve().parent, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from agent_governance_schema import schema_subset_errors  # noqa: E402
import agent_governance_s2_5_recovery as recovery  # noqa: E402
from aiml_gate_receipt_s2_5_host_capture import (  # noqa: E402
    HOST_CAPTURE_SIGNER_CAPABILITY_PATH,
    RECOVERY_HOST_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH,
)
from aiml_gate_receipt_s2e_external_evidence import (  # noqa: E402
    EXTERNAL_WORM_PROVIDER_TRUST_ROOT_PATH,
    PREDECESSOR_REGISTRY_TRUST_ROOT_PATH,
)
from aiml_gate_receipt_s2e_launch import (  # noqa: E402
    S2E_RECEIPT_TRUST_ROOT_PATH,
)
from aiml_gate_receipt_schema_core import (  # noqa: E402
    _contains_github_secret_like_content,
    canonical_digest,
)


SCHEMA_VERSION = "s2e_lw1_operator_action_packet_v1"
INVENTORY_SCHEMA_VERSION = "s2e_lw1_readonly_inventory_v1"
BLOCKED_STATE = "BLOCKED_EXTERNAL_PREREQUISITES_ACTION_PACKET_READY"
SCHEMA_PATH = (
    REPO_ROOT / ".codex" / "schemas" / f"{SCHEMA_VERSION}.schema.json"
)
PATH_STATUS_VALUES = frozenset({
    "ABSENT",
    "NOT_OBSERVED",
    "PRESENT_UNVERIFIED",
    "READY",
})
SERVICE_STATUS_VALUES = frozenset({
    "NOT_CONFIGURED",
    "NOT_OBSERVED",
    "PRESENT_UNVERIFIED",
    "READY",
})
_PATH_PREREQUISITES = (
    (
        "S2E_RECEIPT_TRUST_ROOT",
        str(S2E_RECEIPT_TRUST_ROOT_PATH),
        "ROOT_OWNED_EXACT_0644_JSON_TRUST_PROFILE",
    ),
    (
        "EXTERNAL_WORM_PROVIDER_TRUST_ROOT",
        str(EXTERNAL_WORM_PROVIDER_TRUST_ROOT_PATH),
        "ROOT_OWNED_EXACT_0644_JSON_TRUST_PROFILE",
    ),
    (
        "PREDECESSOR_REGISTRY_TRUST_ROOT",
        str(PREDECESSOR_REGISTRY_TRUST_ROOT_PATH),
        "ROOT_OWNED_EXACT_0644_JSON_TRUST_PROFILE",
    ),
    (
        "RECOVERY_HOST_CAPTURE_TRUST_ROOT",
        str(RECOVERY_HOST_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_AUTHORIZATION_TRUST_ROOT",
        str(recovery.RECOVERY_AUTHORIZATION_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_ANCHOR_TRUST_ROOT",
        str(recovery.RECOVERY_ANCHOR_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_ANCHOR_READBACK_TRUST_ROOT",
        str(recovery.RECOVERY_ANCHOR_READBACK_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_CONSUMPTION_TRUST_ROOT",
        str(recovery.RECOVERY_CONSUMPTION_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_ACTOR_CAPTURE_TRUST_ROOT",
        str(recovery.RECOVERY_ACTOR_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_VERIFIER_CAPTURE_TRUST_ROOT",
        str(recovery.RECOVERY_VERIFIER_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_HOST_CAPTURE_SIGNER_CAPABILITY",
        HOST_CAPTURE_SIGNER_CAPABILITY_PATH,
        "ROOT_OWNED_FIXED_EXECUTABLE_CAPABILITY",
    ),
)
_SERVICE_PREREQUISITES = (
    (
        "EXTERNAL_WORM_COMPLIANCE_DESTINATION",
        "operator-config:external-worm-compliance-destination",
        "S3_OBJECT_LOCK_COMPLIANCE_WITH_NAMED_CREDENTIAL_CHANNEL",
    ),
    (
        "EXTERNAL_WORM_PROVIDER_ATTESTOR",
        "operator-config:external-worm-provider-attestor",
        "DISTINCT_FIXED_ROOT_PLATFORM_OR_EXTERNAL_ATTESTOR",
    ),
    (
        "EXTERNAL_APPEND_ONLY_PREDECESSOR_REGISTRY",
        "operator-config:external-predecessor-registry",
        "DISTINCT_FIXED_ROOT_APPEND_ONLY_SINGLE_USE_REGISTRY",
    ),
)
EXPECTED_PATHS = tuple(item[1] for item in _PATH_PREREQUISITES)
EXPECTED_SERVICE_IDS = tuple(item[0] for item in _SERVICE_PREREQUISITES)
EXPECTED_ACTION_IDS = (
    "PROVISION_FIXED_TRUST_ROOTS",
    "PROVISION_HOST_CAPTURE_SIGNER_CAPABILITY",
    "CONFIGURE_EXTERNAL_WORM_COMPLIANCE_DESTINATION",
    "CONFIGURE_DISTINCT_EXTERNAL_WORM_PROVIDER_ATTESTOR",
    "CONFIGURE_DISTINCT_APPEND_ONLY_PREDECESSOR_REGISTRY",
    "RESUME_W0_AND_LW1_RECEIPT_CHAIN_WITH_FRESH_EVIDENCE",
)


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def packet_digest(packet: dict[str, Any]) -> str:
    return canonical_digest({
        key: value for key, value in packet.items() if key != "packet_digest"
    })


def _strict_inventory(inventory: Any) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(inventory, dict):
        return {}, ["LW1 read-only inventory must be an object"]
    expected_fields = {
        "schema_version",
        "host",
        "observed_at",
        "evidence_class",
        "linux_source_head",
        "linux_worktree_clean",
        "fixed_path_statuses",
        "service_statuses",
        "runtime_units",
        "canonical_roots",
    }
    if set(inventory) != expected_fields:
        errors.append("LW1 read-only inventory fields differ from closed contract")
    if inventory.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        errors.append("LW1 read-only inventory schema_version is invalid")
    if inventory.get("evidence_class") != (
        "UNAUTHENTICATED_READ_ONLY_OBSERVATION"
    ):
        errors.append("LW1 inventory cannot self-promote its evidence class")
    path_statuses = inventory.get("fixed_path_statuses")
    if not isinstance(path_statuses, dict) or set(path_statuses) != set(
        EXPECTED_PATHS
    ):
        errors.append("LW1 inventory fixed path set differs from code-owned set")
    elif any(value not in PATH_STATUS_VALUES for value in path_statuses.values()):
        errors.append("LW1 inventory contains an invalid fixed path status")
    service_statuses = inventory.get("service_statuses")
    if not isinstance(service_statuses, dict) or set(service_statuses) != set(
        EXPECTED_SERVICE_IDS
    ):
        errors.append("LW1 inventory service set differs from code-owned set")
    elif any(
        value not in SERVICE_STATUS_VALUES for value in service_statuses.values()
    ):
        errors.append("LW1 inventory contains an invalid service status")
    if _contains_github_secret_like_content(inventory):
        errors.append("LW1 inventory contains secret-like material")
    return inventory, sorted(set(errors))


def build_s2e_lw1_operator_action_packet(
    *,
    repo_root: Path,
    inventory: Any,
) -> dict[str, Any]:
    """Build one blocked packet; this function cannot emit readiness authority."""

    inventory, errors = _strict_inventory(inventory)
    if errors:
        raise ValueError("; ".join(errors))
    root = repo_root.resolve()
    if _git(root, "status", "--porcelain=v1"):
        raise ValueError("LW1 action packet requires a clean source checkpoint")
    source_head = _git(root, "rev-parse", "HEAD")
    source_tree = _git(root, "rev-parse", "HEAD^{tree}")
    path_statuses = inventory["fixed_path_statuses"]
    service_statuses = inventory["service_statuses"]
    prerequisites = [
        {
            "prerequisite_id": item_id,
            "category": "FIXED_HOST_PATH",
            "locator": path,
            "required_property": required,
            "status": path_statuses[path],
            "blocking": path_statuses[path] != "READY",
            "secret_material_allowed": False,
        }
        for item_id, path, required in _PATH_PREREQUISITES
    ]
    prerequisites.extend(
        {
            "prerequisite_id": item_id,
            "category": "EXTERNAL_SERVICE",
            "locator": locator,
            "required_property": required,
            "status": service_statuses[item_id],
            "blocking": service_statuses[item_id] != "READY",
            "secret_material_allowed": False,
        }
        for item_id, locator, required in _SERVICE_PREREQUISITES
    )
    prerequisites.sort(key=lambda item: item["prerequisite_id"])
    blocked_ids = sorted(
        item["prerequisite_id"] for item in prerequisites if item["blocking"]
    )
    if not blocked_ids:
        raise ValueError(
            "all LW1 external prerequisites appear READY; do not emit a blocked packet"
        )
    packet = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "UNBLOCK_S2E_LW1_EXTERNAL_EVIDENCE_AND_RECEIPT_CHAIN",
        "launch_id": "S2E-LW1-LW5",
        "wave": "S2E-LW1",
        "state": BLOCKED_STATE,
        "source_binding": {
            "implementation_checkpoint_head": source_head,
            "implementation_checkpoint_tree": source_tree,
            "worktree_clean_at_build": True,
        },
        "readonly_observation": {
            "host": inventory["host"],
            "observed_at": inventory["observed_at"],
            "evidence_class": inventory["evidence_class"],
            "inventory_digest": canonical_digest(inventory),
            "linux_source_head": inventory["linux_source_head"],
            "linux_worktree_clean": inventory["linux_worktree_clean"],
            "runtime_units": deepcopy(inventory["runtime_units"]),
            "canonical_roots": deepcopy(inventory["canonical_roots"]),
        },
        "prerequisites": prerequisites,
        "blocked_prerequisite_ids": blocked_ids,
        "required_action_ids": list(EXPECTED_ACTION_IDS),
        "closure_projection": {
            "g0_state": "SOURCE_COMPLETE_RUNTIME_INDETERMINATE",
            "lw1_state": "BLOCKED_EXTERNAL_PREREQUISITES",
            "w0_genesis_receipt_issued": False,
            "lw1_wave_receipt_issued": False,
            "lw1_transition_gate_advance": False,
            "lw2_unlocked": False,
            "s2e_2b_2_closed": False,
            "s2_closed": False,
            "runtime_state": "UNVERIFIED_NOT_OBSERVED",
        },
        "authority_boundaries": {
            "task_issued_authority_count": 0,
            "total_authority_count": 9,
            "admitted_production_effect_receipt_count": 0,
            "total_production_effect_receipt_count": 6,
            "production_runtime_effect_performed_by_task": False,
            "packet_execution_receipt_absent_within_task_scope": True,
            "production_deploy_restart_pg_broker_order_authorized": False,
        },
        "sensitive_material_policy": {
            "policy": "NO_SECRET_MATERIAL_IN_PACKET",
            "credential_channel_name_only": True,
            "private_key_material_permitted": False,
        },
        "next_action": (
            "OPERATOR_PROVISION_EXTERNAL_PREREQUISITES_THEN_RESUME_S2E_LW1"
        ),
    }
    packet["packet_digest"] = packet_digest(packet)
    validation_errors = validate_s2e_lw1_operator_action_packet(
        packet, repo_root=root
    )
    if validation_errors:
        raise ValueError("; ".join(validation_errors))
    return packet


def validate_s2e_lw1_operator_action_packet(
    packet: Any,
    *,
    repo_root: Path,
) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = schema_subset_errors(packet, schema, root_schema=schema)
    if errors or not isinstance(packet, dict):
        return errors
    prerequisites = packet["prerequisites"]
    expected = {
        item_id: (path, required)
        for item_id, path, required in _PATH_PREREQUISITES
    }
    expected.update({
        item_id: (locator, required)
        for item_id, locator, required in _SERVICE_PREREQUISITES
    })
    actual_ids = [item["prerequisite_id"] for item in prerequisites]
    if actual_ids != sorted(expected) or len(actual_ids) != len(set(actual_ids)):
        errors.append("LW1 packet prerequisite IDs differ from code-owned set")
    for item in prerequisites:
        item_id = item["prerequisite_id"]
        if item_id not in expected:
            continue
        if (item["locator"], item["required_property"]) != expected[item_id]:
            errors.append(f"LW1 packet prerequisite binding differs: {item_id}")
        if item["blocking"] != (item["status"] != "READY"):
            errors.append(f"LW1 packet blocker projection differs: {item_id}")
        if item["secret_material_allowed"] is not False:
            errors.append(f"LW1 packet permits secret material: {item_id}")
    expected_blocked = sorted(
        item["prerequisite_id"] for item in prerequisites if item["blocking"]
    )
    if not expected_blocked:
        errors.append("LW1 blocked packet has no blocked prerequisite")
    if packet["blocked_prerequisite_ids"] != expected_blocked:
        errors.append("LW1 packet blocked prerequisite projection differs")
    if tuple(packet["required_action_ids"]) != EXPECTED_ACTION_IDS:
        errors.append("LW1 packet action sequence differs from code-owned sequence")
    binding = packet["source_binding"]
    try:
        head = binding["implementation_checkpoint_head"]
        if _git(repo_root, "rev-parse", f"{head}^{{commit}}") != head:
            errors.append("LW1 packet implementation checkpoint is unavailable")
        if _git(repo_root, "rev-parse", f"{head}^{{tree}}") != binding[
            "implementation_checkpoint_tree"
        ]:
            errors.append("LW1 packet implementation checkpoint tree differs")
    except (OSError, subprocess.CalledProcessError):
        errors.append("LW1 packet source binding cannot be verified")
    if packet["packet_digest"] != packet_digest(packet):
        errors.append("LW1 packet digest is invalid")
    if _contains_github_secret_like_content(packet):
        errors.append("LW1 packet contains secret-like material")
    return sorted(set(errors))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    build.add_argument("--inventory", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    validate.add_argument("--packet", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.action == "build":
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        packet = build_s2e_lw1_operator_action_packet(
            repo_root=args.repo_root,
            inventory=inventory,
        )
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True))
        return 0
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    errors = validate_s2e_lw1_operator_action_packet(
        packet, repo_root=args.repo_root
    )
    print(json.dumps({"status": "PASS" if not errors else "FAIL", "errors": errors}))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
