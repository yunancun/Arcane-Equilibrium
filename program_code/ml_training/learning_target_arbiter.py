"""
MODULE_NOTE
模塊用途：source-only learning target arbiter；從 hash-bound snapshot 選出下一個
expected-value-of-information learning target。
主要類/函數：compute_manifest_hash、compute_runtime_hash、
build_learning_target_runtime、main。
依賴：僅 Python 標準庫；不讀 DB、不連 runtime、不呼叫交易所、不使用 _latest。
硬邊界：scanner/no-order/artifact-count 類 evidence 不能變成 proof/reward/edge/
promotion；輸出 counter/authority flag 永遠為零或 false。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


INPUT_SCHEMA_VERSION = "learning_target_snapshot_manifest_v1"
OUTPUT_SCHEMA_VERSION = "learning_target_runtime_v1"
OBJECTIVE = "expected_value_of_information"
BOUNDARY_LABEL = "SOURCE_ONLY_OFFLINE_P0_P1"

_REQUIRED_MANIFEST_FIELDS = {
    "schema_version",
    "created_at",
    "source_head",
    "snapshot_id",
    "snapshot_kind",
    "objective",
    "latest_alias_used",
    "targets",
    "proof_exclusion",
    "no_authority",
    "manifest_hash",
}
_REQUIRED_TARGET_FIELDS = {
    "target_id",
    "candidate_scope",
    "learning_question",
    "evidence_source_tier",
    "expected_information_gain",
    "uncertainty_reduction",
    "cost_estimate",
    "risk_penalty",
    "staleness_penalty",
    "eligibility",
}
_NUMERIC_TARGET_FIELDS = {
    "expected_information_gain",
    "uncertainty_reduction",
    "cost_estimate",
    "risk_penalty",
    "staleness_penalty",
}
_BLOCKED_SOURCE_TIERS = {
    "scanner",
    "no_order",
    "artifact_count",
    "cleanup",
    "aggregate_fill",
    "healthcheck",
}
_AUTHORITY_FIELD_TOKENS = ("reward", "edge", "proof", "promotion")
_REQUIRED_PROOF_EXCLUSION_DENIALS = {
    "scanner_evidence_is_proof",
    "no_order_evidence_is_reward",
    "artifact_count_evidence_is_edge",
}


class LearningTargetArbiterError(ValueError):
    """Raised for fail-closed source-only contract violations."""


def compute_manifest_hash(manifest: Mapping[str, Any]) -> str:
    """Canonical JSON sha256 over the manifest, excluding only manifest_hash."""
    payload = copy.deepcopy(dict(manifest))
    payload.pop("manifest_hash", None)
    return _canonical_sha256(payload)


def compute_runtime_hash(runtime: Mapping[str, Any]) -> str:
    """Canonical JSON sha256 over the runtime output, excluding only runtime_hash."""
    payload = copy.deepcopy(dict(runtime))
    payload.pop("runtime_hash", None)
    return _canonical_sha256(payload)


def load_snapshot(path: Path) -> dict[str, Any]:
    _reject_latest_path(path, "snapshot")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - platform-specific text
        raise LearningTargetArbiterError(f"snapshot_read_failed:{exc}") from exc
    except json.JSONDecodeError as exc:
        raise LearningTargetArbiterError(f"snapshot_json_invalid:{exc.msg}") from exc
    if not isinstance(raw, dict):
        raise LearningTargetArbiterError("snapshot_not_mapping")
    return raw


def build_learning_target_runtime(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    _validate_snapshot(snapshot)

    ranked_targets = [
        _ranked_target(dict(target)) for target in snapshot["targets"]
    ]
    ranked_targets.sort(key=lambda item: (-item["score"], item["target_id"]))

    selected_target = next(
        (target for target in ranked_targets if target["eligibility"] is True),
        None,
    )
    decision = "SELECT_TARGET" if selected_target is not None else "DEFER_EVIDENCE"

    runtime: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "boundary_label": BOUNDARY_LABEL,
        "objective": OBJECTIVE,
        "input_snapshot_ref": {
            "schema_version": snapshot["schema_version"],
            "source_head": snapshot["source_head"],
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_kind": snapshot["snapshot_kind"],
            "manifest_hash": snapshot["manifest_hash"],
        },
        "selected_target": selected_target,
        "ranked_targets": ranked_targets,
        "decision": decision,
        "proof_exclusion": copy.deepcopy(snapshot["proof_exclusion"]),
        "no_authority": _false_leaf_structure(snapshot["no_authority"]),
        "candidate_matched_fills_count": 0,
        "proof_packet_ready_count": 0,
        "reward_ledger_ready_count": 0,
        "promotion_ready": False,
        "edge_proof_ready": False,
    }
    runtime["runtime_hash"] = compute_runtime_hash(runtime)
    return runtime


def write_runtime_output(runtime: Mapping[str, Any], out_path: Path) -> None:
    _reject_latest_path(out_path, "out")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(runtime, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Source-only learning target arbiter")
    parser.add_argument("--snapshot", required=True, help="Snapshot manifest JSON path")
    parser.add_argument("--out", required=True, help="Explicit runtime output JSON path")
    args = parser.parse_args(argv)

    try:
        snapshot = load_snapshot(Path(args.snapshot))
        runtime = build_learning_target_runtime(snapshot)
        write_runtime_output(runtime, Path(args.out))
    except LearningTargetArbiterError as exc:
        print(f"learning_target_arbiter_error:{exc}", file=sys.stderr)
        return 2
    return 0


def _validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    missing = sorted(_REQUIRED_MANIFEST_FIELDS - set(snapshot))
    if missing:
        raise LearningTargetArbiterError(f"manifest_missing_fields:{','.join(missing)}")
    if snapshot.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise LearningTargetArbiterError("schema_version_invalid")
    if snapshot.get("objective") != OBJECTIVE:
        raise LearningTargetArbiterError("objective_invalid")
    if snapshot.get("latest_alias_used") is not False:
        raise LearningTargetArbiterError("latest_alias_used_rejected")
    if "source_path_latest" in snapshot and snapshot.get("source_path_latest") is not False:
        raise LearningTargetArbiterError("source_path_latest_rejected")
    if _contains_latest_source_ref(snapshot):
        raise LearningTargetArbiterError("source_ref_latest_rejected")
    _validate_no_authority(snapshot.get("no_authority"))
    _validate_proof_exclusion(snapshot.get("proof_exclusion"))
    if snapshot.get("manifest_hash") != compute_manifest_hash(snapshot):
        raise LearningTargetArbiterError("manifest_hash_mismatch")
    targets = snapshot.get("targets")
    if not isinstance(targets, list) or not targets:
        raise LearningTargetArbiterError("targets_invalid")
    for target in targets:
        _validate_target(target)


def _validate_target(target: Any) -> None:
    if not isinstance(target, Mapping):
        raise LearningTargetArbiterError("target_not_mapping")
    missing = sorted(_REQUIRED_TARGET_FIELDS - set(target))
    if missing:
        raise LearningTargetArbiterError(f"target_missing_fields:{','.join(missing)}")
    if not isinstance(target.get("target_id"), str) or not target["target_id"]:
        raise LearningTargetArbiterError("target_id_invalid")
    if not isinstance(target.get("eligibility"), bool):
        raise LearningTargetArbiterError("target_eligibility_invalid")
    for field in _NUMERIC_TARGET_FIELDS:
        value = target.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise LearningTargetArbiterError(f"target_numeric_invalid:{field}")
    tier_value = target.get("evidence_source_tier")
    if not isinstance(tier_value, str) or not tier_value.strip():
        raise LearningTargetArbiterError("evidence_source_tier_invalid")
    tier = _normalize_source_tier(tier_value)
    if tier in _BLOCKED_SOURCE_TIERS:
        blocked = _forbidden_authority_fields(target)
        if blocked:
            raise LearningTargetArbiterError(
                f"blocked_source_tier_authority_attempt:{tier}:{blocked[0]}"
            )


def _ranked_target(target: dict[str, Any]) -> dict[str, Any]:
    score = (
        target["expected_information_gain"]
        + target["uncertainty_reduction"]
        - target["cost_estimate"]
        - target["risk_penalty"]
        - target["staleness_penalty"]
    )
    ranked = copy.deepcopy(target)
    ranked["score"] = score
    return ranked


def _validate_no_authority(value: Any) -> None:
    if not isinstance(value, Mapping) or not value:
        raise LearningTargetArbiterError("no_authority_invalid")
    truthy_paths = _truthy_leaf_paths(value)
    if truthy_paths:
        raise LearningTargetArbiterError(f"no_authority_truthy:{truthy_paths[0]}")


def _validate_proof_exclusion(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise LearningTargetArbiterError("proof_exclusion_invalid")
    missing = sorted(_REQUIRED_PROOF_EXCLUSION_DENIALS - set(value))
    if missing:
        raise LearningTargetArbiterError(
            f"proof_exclusion_missing_denials:{','.join(missing)}"
        )
    for key in sorted(_REQUIRED_PROOF_EXCLUSION_DENIALS):
        if _truthy(value.get(key)):
            raise LearningTargetArbiterError(f"proof_exclusion_truthy:{key}")
    truthy_grants = _truthy_authority_grants(value)
    if truthy_grants:
        raise LearningTargetArbiterError(f"proof_exclusion_truthy:{truthy_grants[0]}")


def _truthy_authority_grants(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            normalized = key_text.lower()
            if (
                any(token in normalized for token in _AUTHORITY_FIELD_TOKENS)
                and _truthy(item)
            ):
                found.append(path)
            found.extend(_truthy_authority_grants(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_truthy_authority_grants(item, f"{prefix}[{index}]"))
    return found


def _truthy_leaf_paths(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            found.extend(_truthy_leaf_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_truthy_leaf_paths(item, f"{prefix}[{index}]"))
    elif _truthy(value):
        found.append(prefix)
    return found


def _false_leaf_structure(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _false_leaf_structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_false_leaf_structure(item) for item in value]
    return False


def _forbidden_authority_fields(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            normalized = key_text.lower()
            if any(token in normalized for token in _AUTHORITY_FIELD_TOKENS):
                found.append(path)
            found.extend(_forbidden_authority_fields(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_authority_fields(item, f"{prefix}[{index}]"))
    return found


def _contains_latest_source_ref(value: Any, key_path: str = "") -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            path = f"{key_path}.{key_text}" if key_path else key_text
            if _contains_latest_source_ref(item, path):
                return True
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if _contains_latest_source_ref(item, f"{key_path}[{index}]"):
                return True
    elif isinstance(value, str) and "_latest" in value.lower() and _is_source_ref_key(key_path):
        return True
    return False


def _is_source_ref_key(key_path: str) -> bool:
    normalized = key_path.lower().replace("[", ".[")
    return any(
        "source" in part or "ref" in part or "path" in part
        for part in normalized.split(".")
    )


def _normalize_source_tier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _truthy(value: Any) -> bool:
    return bool(value)


def _reject_latest_path(path: Path, label: str) -> None:
    if any("_latest" in part.lower() for part in path.parts):
        raise LearningTargetArbiterError(f"{label}_path_latest_rejected")


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":  # pragma: no cover - exercised by CLI tests
    raise SystemExit(main())
