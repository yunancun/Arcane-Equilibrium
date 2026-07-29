"""Source-compatibility receipt validation leaf extracted from the central facade."""

from __future__ import annotations

from typing import Any

from aiml_gate_receipt_schema_core import artifact_self_digest


def source_compatibility_receipt_errors(
    artifact: dict[str, Any],
) -> list[str]:
    """Recompute every nested S2.2A manifest identity from its canonical inputs."""

    from ml_training.learning_runtime_manifest import (
        capture_contract_digest as _lrm_capture_digest,
        manifest_self_digest as _lrm_self_digest,
        training_contract_digest as _lrm_training_digest,
    )

    errors: list[str] = []
    manifest = artifact["learning_runtime_manifest"]
    capture = manifest["capture_contract"]
    training = manifest["training_contract"]
    if artifact["self_digest"] != artifact_self_digest(artifact):
        errors.append("source-compatibility receipt self_digest is invalid")
    if capture["digest"] != _lrm_capture_digest(
        capture["inputs"], capture["snapshot_feature_schema_version"]
    ):
        errors.append("capture_contract.digest does not bind its inputs")
    if training["digest"] != _lrm_training_digest(training["components"]):
        errors.append("training_contract.digest does not bind its components")
    if manifest["self_digest"] != _lrm_self_digest(
        manifest["schema_version"],
        manifest["boundary"],
        capture["digest"],
        training["digest"],
    ):
        errors.append("learning_runtime_manifest self_digest is invalid")
    if artifact["learning_runtime_digest"] != manifest["self_digest"]:
        errors.append("learning_runtime_digest does not bind the manifest self_digest")
    if artifact["capture_contract_digest"] != capture["digest"]:
        errors.append("capture_contract_digest does not bind the manifest")
    if artifact["training_contract_digest"] != training["digest"]:
        errors.append("training_contract_digest does not bind the manifest")
    if artifact["migration_fingerprints"] != training["components"][
        "migration_fingerprints"
    ]:
        errors.append("migration_fingerprints do not bind the manifest components")
    return errors


def source_compatibility_receipt_v2_dependency_lock_errors(
    artifact: dict[str, Any],
) -> list[str]:
    """Require the v2 dependency-lock pair used by the manifest digest."""

    components = artifact["learning_runtime_manifest"]["training_contract"][
        "components"
    ]
    dependency_lock = components.get("dependency_lock")
    if not isinstance(dependency_lock, dict) or set(dependency_lock) != {
        "spec_digest",
        "lock_digest",
    }:
        return [
            "source_compatibility_receipt_v2 dependency_lock must be a "
            "{spec_digest, lock_digest} object"
        ]
    return []
