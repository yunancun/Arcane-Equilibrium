#!/usr/bin/env python3
"""Controller-v2 projection and validation for the fixed recovery store.

This module is pure: it cannot open the state root, acquire a lock, persist a
manifest, attach anchor proof, clear recovery state, or perform a lifecycle
effect.  The fixed POSIX store owns those capabilities and supplies one locked
live snapshot for comparison.
"""

from __future__ import annotations

import copy
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (Path(__file__).resolve().parent, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_5_recovery_controller as controller  # noqa: E402


def _trusted_now() -> str:
    """Return code-owned current UTC time for fresh admission validation."""

    return datetime.now(timezone.utc).isoformat()


def build_successor_manifest(
    controller_state: Any,
    previous_manifest: Any,
    snapshot: dict[str, Any],
    *,
    source_head: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Build one exact v2 wrapper after validating every predecessor edge."""

    errors = controller.validate_controller_artifact(controller_state)
    errors.extend(
        controller.validate_fresh_controller_admission(
            controller_state,
            trusted_now=_trusted_now(),
        )
    )
    errors.extend(controller.validate_controller_artifact(previous_manifest))
    if errors or not isinstance(controller_state, dict) or not isinstance(
        previous_manifest, dict
    ):
        return None, errors
    errors.extend(
        controller.validate_controller_state_successor(
            previous_manifest.get("controller_state"),
            controller_state,
        )
    )
    subject = controller_state.get("candidate_subject")
    if errors or not isinstance(subject, dict):
        return None, errors
    candidate = {
        "schema_version": controller.MANIFEST_SCHEMA,
        "store_id": controller.derive_store_id(snapshot["state_root_id"]),
        "stable_root_id": subject.get("stable_root_id"),
        "state_root_id": snapshot["state_root_id"],
        "source_head": source_head,
        "generation": subject.get("generation"),
        "phase": subject.get("phase"),
        "anchor_progress": subject.get("anchor_progress"),
        "previous_manifest_digest": previous_manifest.get("self_digest"),
        "controller_state": copy.deepcopy(controller_state),
        "controller_state_digest": controller_state.get("self_digest"),
        "pending_outbox": copy.deepcopy(
            controller_state.get("pending_outbox")
        ),
        "pending_outbox_digest": controller_state.get(
            "pending_outbox_digest"
        ),
        "attached_anchor_proof": copy.deepcopy(
            controller_state.get("attached_anchor_proof")
        ),
        "attached_anchor_proof_digest": controller_state.get(
            "attached_anchor_proof_digest"
        ),
        "state_root_identity": copy.deepcopy(
            snapshot["state_root_identity"]
        ),
        "journal_inventory": copy.deepcopy(
            snapshot["controller_journal_inventory"]
        ),
        "journal_set_digest": snapshot[
            "controller_journal_set_digest"
        ],
        "replay_ledger": copy.deepcopy(
            snapshot["controller_replay_ledger"]
        ),
        "trust_status": "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED",
        "side_effect_class": "DISPOSABLE_TEST",
        "target_class": "disposable_systemd",
        "target_profile_id": subject.get("target_profile_id"),
        "production_effect": False,
        "production_authority": False,
        "production_effect_count": 0,
    }
    candidate["self_digest"] = central_validator.artifact_self_digest(
        candidate
    )
    errors.extend(
        controller.validate_manifest_successor(
            previous_manifest,
            candidate,
        )
    )
    errors.extend(
        validate_manifest_against_snapshot(
            candidate,
            snapshot,
            source_head=source_head,
        )
    )
    return (None, errors) if errors else (candidate, [])


def validate_manifest_against_snapshot(
    manifest: Any,
    snapshot: dict[str, Any],
    *,
    source_head: str,
) -> list[str]:
    """Validate one v2 manifest against the exact locked live projection."""

    errors = controller.validate_controller_artifact(manifest)
    if errors or not isinstance(manifest, dict):
        return errors
    expected = {
        "state_root_identity": snapshot["state_root_identity"],
        "state_root_id": snapshot["state_root_id"],
        "journal_inventory": snapshot["controller_journal_inventory"],
        "journal_set_digest": snapshot[
            "controller_journal_set_digest"
        ],
        "replay_ledger": snapshot["controller_replay_ledger"],
        "source_head": source_head,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(f"v2 manifest {key} differs from locked live state")
    if manifest.get("store_id") != controller.derive_store_id(
        snapshot["state_root_id"]
    ):
        errors.append("v2 manifest store id differs from code-owned live root")
    state = manifest.get("controller_state")
    subject = (
        state.get("candidate_subject") if isinstance(state, dict) else None
    )
    if isinstance(subject, dict):
        if subject.get("state_root_identity") != snapshot[
            "state_root_identity"
        ]:
            errors.append(
                "v2 controller state-root identity differs from live root"
            )
        if subject.get("journal_inventory") != snapshot[
            "controller_journal_inventory"
        ]:
            errors.append(
                "v2 controller journal inventory differs from live root"
            )
        if subject.get("replay_ledger") != snapshot[
            "controller_replay_ledger"
        ]:
            errors.append(
                "v2 controller replay projection differs from live root"
            )
    if manifest.get("self_digest") != central_validator.artifact_self_digest(
        manifest
    ):
        errors.append("v2 manifest self digest does not re-derive")
    return errors
