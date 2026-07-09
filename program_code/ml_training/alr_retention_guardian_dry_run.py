"""
MODULE_NOTE
Source-only ALR retention guardian dry-run contract; emits one hash-bound JSON
file and grants no runtime, exchange, proof, promotion, order, or probe authority.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


INPUT_SCHEMA_VERSION = "retention_guardian_artifact_manifest_v1"
OUTPUT_SCHEMA_VERSION = "retention_guardian_dry_run_v1"
BOUNDARY_LABEL = "SOURCE_ONLY_OFFLINE_P0_P1"

STATE_PROOF_OR_AUDIT_PROTECTED = "PROOF_OR_AUDIT_PROTECTED"
STATE_DISPUTED_PROTECTED = "DISPUTED_PROTECTED"
STATE_NEGATIVE_EXAMPLE_PROTECTED = "NEGATIVE_EXAMPLE_PROTECTED"
STATE_LINEAGE_PROVENANCE_PROTECTED = "LINEAGE_PROVENANCE_PROTECTED"
STATE_REFERENCE_UNKNOWN_PROTECTED = "REFERENCE_UNKNOWN_PROTECTED"
STATE_REBUILDABLE_SCRATCH_CANDIDATE = "REBUILDABLE_SCRATCH_CANDIDATE"
STATE_QUARANTINE_CANDIDATE_DRY_RUN = "QUARANTINE_CANDIDATE_DRY_RUN"
STATE_TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY = "TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY"

ALLOWED_RETENTION_STATES = frozenset(
    (
        STATE_PROOF_OR_AUDIT_PROTECTED, STATE_DISPUTED_PROTECTED,
        STATE_NEGATIVE_EXAMPLE_PROTECTED, STATE_LINEAGE_PROVENANCE_PROTECTED,
        STATE_REFERENCE_UNKNOWN_PROTECTED, STATE_REBUILDABLE_SCRATCH_CANDIDATE,
        STATE_QUARANTINE_CANDIDATE_DRY_RUN,
        STATE_TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY,
    )
)

ARTIFACT_FIELDS = tuple(
    """
    artifact_id canonical_path content_sha256 size mtime producer schema_version
    candidate_identity source_hash input_hashes order_ids fill_ids context_ids
    outbound_refs inbound_refs report_refs todo_refs adr_refs amd_refs _latest_refs
    classification_reason retention_state blockers rebuild_or_disposable_proof
    proposed_action
    """.split()
)

STOP_RETENTION_RISK = "STOP_RETENTION_RISK"
DRY_RUN_OUTPUT_NAME = "retention_guardian_dry_run_v1.json"

_TOP_OUTPUT_FIELDS = tuple(
    "schema_version boundary_label dry_run_only input_manifest_ref reference_graph "
    "reference_graph_hash artifacts authority_counters no_authority manifest_hash".split()
)
_INPUT_REQUIRED_FIELDS = set(
    "schema_version boundary_label created_at source_head latest_alias_used "
    "no_authority artifacts manifest_hash".split()
)
_REF_FIELDS = (
    "outbound_refs",
    "inbound_refs",
    "report_refs",
    "todo_refs",
    "adr_refs",
    "amd_refs",
    "context_ids",
)
_HASH_REF_FIELDS = ("input_hashes",)
_LIST_FIELDS = tuple(
    "input_hashes order_ids fill_ids context_ids outbound_refs inbound_refs "
    "report_refs todo_refs adr_refs amd_refs _latest_refs blockers".split()
)
_AUTHORITY_COUNTER_KEYS = tuple(
    "runtime_mutation_count pg_contact_count ipc_contact_count exchange_contact_count "
    "decision_lease_count order_or_probe_count cost_gate_change_count serving_change_count "
    "proof_or_promotion_count live_or_mainnet_count artifact_mutation_count".split()
)
_NO_AUTHORITY_KEYS = tuple(
    "runtime pg ipc bybit official_mcp decision_lease order_or_probe cost_gate "
    "latest_writer serving proof_or_promotion physical_artifact_mutation cron_or_daemon "
    "live_or_mainnet".split()
)
_PATH_FORBIDDEN_TERMS = set(
    "runtime pg postgres postgresql database ipc bybit mcp decision lease order probe "
    "serving promotion promote proof cron daemon scheduler service env live mainnet".split()
)
_PROOF_AUDIT_TERMS = tuple(
    "proof audit reward ledger order fill fee slippage decision_lease authorization "
    "guardian risk_governor reconciliation".split()
)
_DISPUTED_TERMS = ("disputed", "dispute")
_NEGATIVE_TERMS = tuple(
    "negative falsification failed blocked rotated cleanup unattributed proof_excluded "
    "hidden_oos control repeat".split()
)
_LINEAGE_TERMS = ("lineage", "provenance", "source", "input", "context", "todo", "adr", "amd")
_HEX64_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_TRUTHY_STRINGS = set(
    "1 true yes y on enabled enable grant granted allow allowed active approved present".split()
)


@dataclass(frozen=True)
class RetentionGuardianDryRunValidation:
    valid: bool
    reason: str
    reasons: tuple[str, ...]
    tombstone_count: int = 0
    stop_retention_risk_count: int = 0


class RetentionGuardianDryRunError(ValueError):
    """Raised when the CLI cannot safely produce the requested dry-run file."""


def compute_artifact_manifest_hash(manifest: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(manifest))
    payload.pop("manifest_hash", None)
    return _canonical_sha256(payload)


def compute_reference_graph_hash(reference_graph: Mapping[str, Any]) -> str:
    return _canonical_sha256(copy.deepcopy(dict(reference_graph)))


def compute_retention_guardian_dry_run_hash(dry_run: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(dry_run))
    payload.pop("manifest_hash", None)
    return _canonical_sha256(payload)


def build_retention_guardian_dry_run(artifact_manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(artifact_manifest, Mapping):
        raise RetentionGuardianDryRunError("artifact_manifest_not_mapping")

    manifest = copy.deepcopy(dict(artifact_manifest))
    raw_artifacts = manifest.get("artifacts")
    artifacts: list[dict[str, Any]]
    if isinstance(raw_artifacts, Sequence) and not isinstance(
        raw_artifacts, (str, bytes, bytearray)
    ):
        artifacts = [
            copy.deepcopy(dict(item)) if isinstance(item, Mapping) else {"artifact_id": ""}
            for item in raw_artifacts
        ]
    else:
        artifacts = []

    rows = [_contract_row(item, index) for index, item in enumerate(artifacts)]
    manifest_reasons = _manifest_stop_reasons(manifest)
    graph_base = _build_reference_graph(rows)
    direct_states = {
        row["artifact_id"]: _direct_protected_state(row)
        for row in rows
        if _text(row.get("artifact_id"))
    }
    direct_protected_ids = {
        artifact_id for artifact_id, state in direct_states.items() if state is not None
    }
    transitive_protected_ids = _transitive_protected_ids(
        graph_base["edges"], direct_protected_ids
    )
    inbound_counts = _inbound_counts(graph_base["edges"])

    output_rows = [
        _classify_row(
            row=row,
            graph=graph_base,
            manifest_reasons=manifest_reasons,
            direct_state=direct_states.get(row["artifact_id"]),
            transitive_protected=row["artifact_id"] in transitive_protected_ids,
            inbound_count=inbound_counts.get(row["artifact_id"], 0),
        )
        for row in rows
    ]
    reference_graph = dict(graph_base)
    reference_graph["protected_artifact_ids"] = sorted(
        row["artifact_id"]
        for row in output_rows
        if row["retention_state"] != STATE_TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY
    )
    reference_graph["tombstone_candidate_ids"] = sorted(
        row["artifact_id"]
        for row in output_rows
        if row["retention_state"] == STATE_TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY
    )
    reference_graph_hash = compute_reference_graph_hash(reference_graph)

    dry_run: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "boundary_label": BOUNDARY_LABEL,
        "dry_run_only": True,
        "input_manifest_ref": {
            "schema_version": _text(manifest.get("schema_version")),
            "boundary_label": _text(manifest.get("boundary_label")),
            "created_at": _text(manifest.get("created_at")),
            "source_head": _text(manifest.get("source_head")),
            "manifest_hash": _text(manifest.get("manifest_hash")),
            "computed_manifest_hash": _safe_compute_manifest_hash(manifest),
            "manifest_stop_reasons": manifest_reasons,
        },
        "reference_graph": reference_graph,
        "reference_graph_hash": reference_graph_hash,
        "artifacts": output_rows,
        "authority_counters": {key: 0 for key in _AUTHORITY_COUNTER_KEYS},
        "no_authority": _no_authority(),
        "manifest_hash": "",
    }
    dry_run["manifest_hash"] = compute_retention_guardian_dry_run_hash(dry_run)
    return dry_run


def validate_retention_guardian_dry_run(dry_run: Any) -> RetentionGuardianDryRunValidation:
    if not isinstance(dry_run, Mapping):
        return _validation(False, "dry_run_not_mapping")
    reasons: list[str] = []
    if set(dry_run.keys()) != set(_TOP_OUTPUT_FIELDS):
        reasons.append("top_level_fields_mismatch")
    if dry_run.get("schema_version") != OUTPUT_SCHEMA_VERSION:
        reasons.append("schema_version_invalid")
    if dry_run.get("boundary_label") != BOUNDARY_LABEL:
        reasons.append("boundary_label_invalid")
    if dry_run.get("dry_run_only") is not True:
        reasons.append("dry_run_only_not_true")
    artifacts = dry_run.get("artifacts")
    if not isinstance(artifacts, list):
        reasons.append("artifacts_not_list")
        artifacts = []
    for index, row in enumerate(artifacts):
        if not isinstance(row, Mapping):
            reasons.append(f"artifact_not_mapping:{index}")
            continue
        if set(row.keys()) != set(ARTIFACT_FIELDS):
            reasons.append(f"artifact_fields_mismatch:{index}")
        if row.get("retention_state") not in ALLOWED_RETENTION_STATES:
            reasons.append(f"artifact_retention_state_unknown:{index}")
        if row.get("retention_state") != STATE_TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY:
            blockers = row.get("blockers")
            if not isinstance(blockers, list) or STOP_RETENTION_RISK not in blockers:
                reasons.append(f"protected_artifact_missing_stop:{index}")
    if _mapping(dry_run.get("authority_counters")) != {
        key: 0 for key in _AUTHORITY_COUNTER_KEYS
    }:
        reasons.append("authority_counters_not_zeroed")
    if _mapping(dry_run.get("no_authority")) != _no_authority():
        reasons.append("no_authority_not_false_only")
    reference_graph = _mapping(dry_run.get("reference_graph"))
    if dry_run.get("reference_graph_hash") != compute_reference_graph_hash(reference_graph):
        reasons.append("reference_graph_hash_mismatch")
    manifest_hash = _text(dry_run.get("manifest_hash"))
    if not _is_hex64(manifest_hash):
        reasons.append("manifest_hash_malformed")
    elif manifest_hash != compute_retention_guardian_dry_run_hash(dry_run):
        reasons.append("manifest_hash_mismatch")
    if reasons:
        return _validation(
            False,
            reasons[0],
            reasons,
            tombstone_count=_tombstone_count(artifacts),
            stop_retention_risk_count=_stop_count(artifacts),
        )
    return _validation(
        True,
        "ok",
        tombstone_count=_tombstone_count(artifacts),
        stop_retention_risk_count=_stop_count(artifacts),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Source-only ALR retention guardian dry-run")
    parser.add_argument("--artifact-manifest", required=True, help="Artifact manifest JSON path")
    parser.add_argument("--out-dir", required=True, help="Output directory for dry-run JSON")
    args = parser.parse_args(argv)

    manifest_path = Path(args.artifact_manifest)
    out_dir = Path(args.out_dir)
    out_path = out_dir / DRY_RUN_OUTPUT_NAME
    try:
        _reject_latest_path(manifest_path, "artifact_manifest")
        _reject_latest_path(out_dir, "out_dir")
        _reject_forbidden_output_path(out_dir)
        _reject_symlinked_existing_path(out_dir, "out_dir")
        resolved_out_dir = out_dir.resolve(strict=False)
        _reject_latest_path(resolved_out_dir, "out_dir_resolved")
        _reject_forbidden_output_path(resolved_out_dir)
        if out_path.is_symlink():
            raise RetentionGuardianDryRunError("output_path_is_symlink")
        if out_dir.exists() and any(out_dir.iterdir()):
            raise RetentionGuardianDryRunError("out_dir_not_empty")
        if out_path.exists():
            raise RetentionGuardianDryRunError("output_exists")
        manifest = _load_json(manifest_path)
        dry_run = build_retention_guardian_dry_run(manifest)
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            with out_path.open("x", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(dry_run, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
                )
        except FileExistsError as exc:
            raise RetentionGuardianDryRunError("output_exists") from exc
    except RetentionGuardianDryRunError as exc:
        print(f"retention_guardian_dry_run_error:{exc}", file=sys.stderr)
        return 2
    return 0


def _contract_row(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    row: dict[str, Any] = {}
    raw_keys = set(raw)
    missing_fields = sorted(set(ARTIFACT_FIELDS) - raw_keys)
    extra_fields = sorted(raw_keys - set(ARTIFACT_FIELDS))
    for field in ARTIFACT_FIELDS:
        if field in raw:
            row[field] = copy.deepcopy(raw[field])
        else:
            row[field] = _default_field_value(field, index)
    blockers = _list(row.get("blockers"))
    if "blockers" in raw and not isinstance(raw.get("blockers"), list):
        blockers.append("blockers_not_list")
    blockers.extend(f"{field}_missing" for field in missing_fields)
    blockers.extend(f"{field}_unexpected" for field in extra_fields)
    row["blockers"] = _dedupe(blockers)
    return row


def _default_field_value(field: str, index: int) -> Any:
    if field == "artifact_id":
        return f"invalid_artifact_{index}"
    if field in _LIST_FIELDS:
        return []
    if field == "candidate_identity":
        return {}
    if field == "rebuild_or_disposable_proof":
        return {}
    if field == "retention_state":
        return STATE_LINEAGE_PROVENANCE_PROTECTED
    if field == "size":
        return 0
    if field == "mtime":
        return 0.0
    return ""


def _manifest_stop_reasons(manifest: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    missing = sorted(_INPUT_REQUIRED_FIELDS - set(manifest))
    reasons.extend(f"manifest_{field}_missing" for field in missing)
    if manifest.get("schema_version") != INPUT_SCHEMA_VERSION:
        reasons.append("schema_version_invalid")
    if manifest.get("boundary_label") != BOUNDARY_LABEL:
        reasons.append("boundary_label_invalid")
    if manifest.get("latest_alias_used") is not False:
        reasons.append("latest_alias_used_not_false")
    if not isinstance(manifest.get("artifacts"), list):
        reasons.append("artifacts_not_list")
    reasons.extend(_false_leaf_reasons(manifest.get("no_authority"), "no_authority"))
    manifest_hash = _text(manifest.get("manifest_hash"))
    if not _is_hex64(manifest_hash):
        reasons.append("manifest_hash_missing_or_malformed")
    else:
        computed = _safe_compute_manifest_hash(manifest)
        if computed != manifest_hash:
            reasons.append("manifest_hash_mismatch")
    return _dedupe(reasons)


def _safe_compute_manifest_hash(manifest: Mapping[str, Any]) -> str:
    try:
        return compute_artifact_manifest_hash(manifest)
    except (TypeError, ValueError):
        return ""


def _false_leaf_reasons(value: Any, path: str) -> list[str]:
    if not isinstance(value, Mapping) or not value:
        return [f"{path}_invalid"]
    reasons: list[str] = []
    for key, child in value.items():
        child_path = f"{path}.{key}"
        if isinstance(child, Mapping):
            reasons.extend(_false_leaf_reasons(child, child_path))
        elif isinstance(child, list):
            for index, item in enumerate(child):
                reasons.extend(_false_leaf_reasons({str(index): item}, child_path))
        elif child is not False:
            reasons.append(f"{child_path}_not_false")
    return reasons


def _build_reference_graph(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ids = [_text(row.get("artifact_id")) for row in rows]
    id_counts = {item: ids.count(item) for item in ids if item}
    ambiguous_ids = sorted(item for item, count in id_counts.items() if count > 1)
    known_ids = {item for item in ids if item and item not in ambiguous_ids}
    content_hash_to_ids: dict[str, list[str]] = {}
    for row in rows:
        artifact_id = _text(row.get("artifact_id"))
        content_hash = _strip_sha(_text(row.get("content_sha256")))
        if artifact_id in known_ids and _is_hex64(content_hash):
            content_hash_to_ids.setdefault(content_hash, []).append(artifact_id)
    content_hash_targets = {
        content_hash: artifact_ids[0]
        for content_hash, artifact_ids in content_hash_to_ids.items()
        if len(artifact_ids) == 1
    }
    ambiguous_content_hashes = sorted(
        content_hash
        for content_hash, artifact_ids in content_hash_to_ids.items()
        if len(artifact_ids) > 1
    )
    path_counts: dict[str, int] = {}
    for row in rows:
        path_text = _text(row.get("canonical_path"))
        if path_text:
            path_counts[path_text] = path_counts.get(path_text, 0) + 1
    ambiguous_paths = sorted(path for path, count in path_counts.items() if count > 1)

    edges: list[dict[str, str]] = []
    unknown_refs: list[dict[str, str]] = []
    hash_refs: list[dict[str, str]] = []
    for row in rows:
        source_id = _text(row.get("artifact_id"))
        if not source_id:
            continue
        for field in _REF_FIELDS:
            for ref in _refs(row.get(field)):
                edge = {"from": source_id, "to": ref, "field": field}
                if ref in known_ids:
                    edges.append(edge)
                else:
                    unknown_refs.append(
                        {"artifact_id": source_id, "ref": ref, "field": field}
                    )
        for field in _HASH_REF_FIELDS:
            for ref in _refs(row.get(field)):
                content_hash_ref = _strip_sha(ref)
                if ref in known_ids:
                    edges.append({"from": source_id, "to": ref, "field": field})
                elif content_hash_ref in content_hash_targets:
                    edges.append(
                        {
                            "from": source_id,
                            "to": content_hash_targets[content_hash_ref],
                            "field": field,
                        }
                    )
                elif content_hash_ref in content_hash_to_ids:
                    unknown_refs.append(
                        {"artifact_id": source_id, "ref": ref, "field": field}
                    )
                elif _is_hex64(content_hash_ref):
                    hash_refs.append(
                        {"artifact_id": source_id, "hash": content_hash_ref, "field": field}
                    )
                else:
                    unknown_refs.append(
                        {"artifact_id": source_id, "ref": ref, "field": field}
                    )
    return {
        "artifact_ids": sorted(ids),
        "edges": sorted(edges, key=lambda item: (item["from"], item["to"], item["field"])),
        "hash_refs": sorted(
            hash_refs, key=lambda item: (item["artifact_id"], item["hash"], item["field"])
        ),
        "unknown_refs": sorted(
            unknown_refs, key=lambda item: (item["artifact_id"], item["ref"], item["field"])
        ),
        "ambiguous_artifact_ids": ambiguous_ids,
        "ambiguous_content_hashes": ambiguous_content_hashes,
        "ambiguous_paths": ambiguous_paths,
    }


def _classify_row(
    *,
    row: Mapping[str, Any],
    graph: Mapping[str, Any],
    manifest_reasons: Sequence[str],
    direct_state: str | None,
    transitive_protected: bool,
    inbound_count: int,
) -> dict[str, Any]:
    artifact_id = _text(row.get("artifact_id"))
    reasons = list(manifest_reasons)
    reasons.extend(_artifact_schema_reasons(row))
    reasons.extend(_artifact_metadata_reasons(row))
    reasons.extend(_text(item) for item in _list(row.get("blockers")) if _text(item))
    if artifact_id in set(graph.get("ambiguous_artifact_ids", ())):
        reasons.append("artifact_id_ambiguous")
    if _text(row.get("canonical_path")) in set(graph.get("ambiguous_paths", ())):
        reasons.append("canonical_path_ambiguous")
    if any(item.get("artifact_id") == artifact_id for item in graph.get("unknown_refs", ())):
        reasons.append("reference_unknown")
    if _non_empty(row.get("_latest_refs")):
        reasons.append("latest_refs_non_empty")
    if transitive_protected and direct_state is None:
        reasons.append("transitive_protected_reference")
    outgoing_count = sum(1 for item in graph.get("edges", ()) if item.get("from") == artifact_id)
    if direct_state is None and (outgoing_count or inbound_count):
        reasons.append("reference_contact_not_transitively_empty")

    rebuild_valid = _rebuild_or_disposable_proof_valid(row.get("rebuild_or_disposable_proof"))
    if direct_state is None and not rebuild_valid:
        reasons.append("rebuild_or_disposable_proof_invalid")

    output = {field: copy.deepcopy(row[field]) for field in ARTIFACT_FIELDS}
    if direct_state is not None:
        state = direct_state
        if not reasons:
            reasons.append("protected_class_contact")
    elif "reference_unknown" in reasons:
        state = STATE_REFERENCE_UNKNOWN_PROTECTED
    elif reasons:
        state = STATE_LINEAGE_PROVENANCE_PROTECTED
    else:
        state = STATE_TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY

    if state == STATE_TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY:
        output["classification_reason"] = "ordinary_rebuildable_scratch_unreferenced"
        output["blockers"] = []
        output["proposed_action"] = "TOMBSTONE_STAGE_1_DRY_RUN_ONLY"
    else:
        blockers = _dedupe([*_list(row.get("blockers")), STOP_RETENTION_RISK, *reasons])
        output["classification_reason"] = _classification_reason(state, blockers)
        output["blockers"] = blockers
        output["proposed_action"] = "NONE_PROTECTED"
    output["retention_state"] = state
    return output


def _artifact_schema_reasons(row: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in ARTIFACT_FIELDS:
        if field not in row:
            reasons.append(f"{field}_missing")
    for field in _LIST_FIELDS:
        if field in row and not isinstance(row.get(field), list):
            reasons.append(f"{field}_not_list")
    retention_state = _text(row.get("retention_state"))
    if retention_state not in ALLOWED_RETENTION_STATES:
        reasons.append("retention_state_unknown")
    if not _text(row.get("artifact_id")):
        reasons.append("artifact_id_missing")
    if not _text(row.get("canonical_path")):
        reasons.append("canonical_path_missing")
    if row.get("size") is None:
        reasons.append("size_missing")
    if row.get("mtime") is None:
        reasons.append("mtime_missing")
    source_hash = _text(row.get("source_hash"))
    if source_hash and not _is_hex64(_strip_sha(source_hash)):
        reasons.append("source_hash_malformed")
    return reasons


def _artifact_metadata_reasons(row: Mapping[str, Any]) -> list[str]:
    path_text = _text(row.get("canonical_path"))
    if not path_text:
        return []
    path = Path(path_text)
    if _path_has_latest(path):
        return ["canonical_path_latest_rejected"]
    try:
        if path.is_symlink():
            return ["canonical_path_is_symlink"]
        stat = path.stat()
        if not path.is_file():
            return ["canonical_path_not_file"]
        data = path.read_bytes()
    except OSError:
        return ["canonical_path_unreadable"]
    reasons: list[str] = []
    content_sha = _strip_sha(_text(row.get("content_sha256")))
    if not _is_hex64(content_sha) or hashlib.sha256(data).hexdigest() != content_sha:
        reasons.append("content_sha256_mismatch")
    if _coerce_int(row.get("size")) != stat.st_size:
        reasons.append("size_mismatch")
    if not _mtime_matches(row.get("mtime"), stat.st_mtime):
        reasons.append("mtime_mismatch")
    return reasons


def _direct_protected_state(row: Mapping[str, Any]) -> str | None:
    declared = _text(row.get("retention_state"))
    if declared in {
        STATE_PROOF_OR_AUDIT_PROTECTED,
        STATE_DISPUTED_PROTECTED,
        STATE_NEGATIVE_EXAMPLE_PROTECTED,
        STATE_LINEAGE_PROVENANCE_PROTECTED,
        STATE_REFERENCE_UNKNOWN_PROTECTED,
    }:
        return declared
    haystack = _artifact_haystack(row)
    if _any_term(haystack, _DISPUTED_TERMS):
        return STATE_DISPUTED_PROTECTED
    if _any_term(haystack, _NEGATIVE_TERMS):
        return STATE_NEGATIVE_EXAMPLE_PROTECTED
    if _non_empty(row.get("order_ids")) or _non_empty(row.get("fill_ids")):
        return STATE_PROOF_OR_AUDIT_PROTECTED
    if _non_empty(row.get("report_refs")) or _any_term(haystack, _PROOF_AUDIT_TERMS):
        return STATE_PROOF_OR_AUDIT_PROTECTED
    if (
        _text(row.get("source_hash"))
        or _non_empty(row.get("input_hashes"))
        or _non_empty(row.get("context_ids"))
        or _non_empty(row.get("todo_refs"))
        or _non_empty(row.get("adr_refs"))
        or _non_empty(row.get("amd_refs"))
        or _any_term(haystack, _LINEAGE_TERMS)
    ):
        return STATE_LINEAGE_PROVENANCE_PROTECTED
    if declared == STATE_QUARANTINE_CANDIDATE_DRY_RUN:
        return STATE_LINEAGE_PROVENANCE_PROTECTED
    return None


def _artifact_haystack(row: Mapping[str, Any]) -> str:
    parts = [
        _text(row.get("artifact_id")),
        _text(row.get("canonical_path")),
        _text(row.get("producer")),
        _text(row.get("schema_version")),
        _text(row.get("classification_reason")),
        _text(row.get("retention_state")),
        _text(row.get("proposed_action")),
    ]
    return " ".join(parts).lower()


def _any_term(haystack: str, terms: Iterable[str]) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", haystack.lower())
    return any(term in normalized for term in terms)


def _transitive_protected_ids(
    edges: Sequence[Mapping[str, str]], protected_ids: set[str]
) -> set[str]:
    reverse: dict[str, set[str]] = {}
    for edge in edges:
        reverse.setdefault(edge["to"], set()).add(edge["from"])
    found = set(protected_ids)
    frontier = list(protected_ids)
    while frontier:
        current = frontier.pop()
        for predecessor in reverse.get(current, set()):
            if predecessor not in found:
                found.add(predecessor)
                frontier.append(predecessor)
    return found


def _inbound_counts(edges: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in edges:
        counts[edge["to"]] = counts.get(edge["to"], 0) + 1
    return counts


def _rebuild_or_disposable_proof_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    truthy_rebuild = _truthy(value.get("rebuildable")) or _truthy(value.get("disposable"))
    status = _text(value.get("status")).lower()
    status_valid = status in {
        "rebuildable",
        "disposable",
        "rebuild_hash_match",
        "disposable_confirmed",
        "rebuildable_confirmed",
    }
    proof_complete = value.get("proof_complete")
    if proof_complete is None:
        proof_complete = value.get("complete")
    return (truthy_rebuild or status_valid) and proof_complete is not False


def _classification_reason(state: str, blockers: Sequence[str]) -> str:
    if state == STATE_REFERENCE_UNKNOWN_PROTECTED:
        return "protected:unknown_reference"
    if state == STATE_PROOF_OR_AUDIT_PROTECTED:
        return "protected:proof_or_audit_contact"
    if state == STATE_DISPUTED_PROTECTED:
        return "protected:disputed_contact"
    if state == STATE_NEGATIVE_EXAMPLE_PROTECTED:
        return "protected:negative_or_falsification_contact"
    if "transitive_protected_reference" in blockers:
        return "protected:transitive_reference_contact"
    return "protected:lineage_or_fail_closed_contact"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RetentionGuardianDryRunError(f"artifact_manifest_read_failed:{exc}") from exc
    except json.JSONDecodeError as exc:
        raise RetentionGuardianDryRunError(
            f"artifact_manifest_json_invalid:{exc.msg}"
        ) from exc
    if not isinstance(raw, dict):
        raise RetentionGuardianDryRunError("artifact_manifest_not_mapping")
    return raw


def _reject_latest_path(path: Path, label: str) -> None:
    if _path_has_latest(path):
        raise RetentionGuardianDryRunError(f"{label}_path_latest_rejected")


def _reject_forbidden_output_path(path: Path) -> None:
    for part in path.parts:
        lowered = part.lower()
        tokens = set(_path_tokens(lowered))
        if "cost" in tokens and "gate" in tokens:
            raise RetentionGuardianDryRunError("out_dir_path_forbidden_term:cost_gate")
        forbidden = sorted(tokens & _PATH_FORBIDDEN_TERMS)
        if forbidden:
            raise RetentionGuardianDryRunError(
                f"out_dir_path_forbidden_term:{forbidden[0]}"
            )


def _reject_symlinked_existing_path(path: Path, label: str) -> None:
    current = Path(path.anchor) if path.is_absolute() else Path.cwd()
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current = current / part
        try:
            current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise RetentionGuardianDryRunError(f"{label}_path_lstat_failed:{exc}") from exc
        if current.is_symlink():
            raise RetentionGuardianDryRunError(f"{label}_path_symlink_rejected")


def _path_has_latest(path: Path) -> bool:
    return any("_latest" in part.lower() for part in path.parts)


def _path_tokens(value: str) -> list[str]:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return [token for token in re.split(r"[^a-z0-9]+", normalized.lower()) if token]


def _refs(value: Any) -> list[str]:
    refs: list[str] = []
    if not isinstance(value, list):
        return refs
    for item in value:
        if isinstance(item, str) and item:
            refs.append(item)
        elif isinstance(item, Mapping):
            for key in ("artifact_id", "artifact_ref", "target_artifact_id", "ref"):
                ref = _text(item.get(key))
                if ref:
                    refs.append(ref)
                    break
    return _dedupe(refs)


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _non_empty(value: Any) -> bool:
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return bool(_text(value))


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_STRINGS
    return bool(value)


def _is_hex64(value: str) -> bool:
    return bool(_HEX64_RE.fullmatch(value))


def _strip_sha(value: str) -> str:
    return value.removeprefix("sha256:")


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _mtime_matches(declared: Any, actual: float) -> bool:
    if isinstance(declared, bool):
        return False
    try:
        declared_float = float(declared)
    except (TypeError, ValueError):
        return False
    return abs(declared_float - actual) <= 1e-3


def _dedupe(values: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    out: list[Any] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _no_authority() -> dict[str, bool]:
    return {key: False for key in _NO_AUTHORITY_KEYS}


def _validation(
    valid: bool,
    reason: str,
    reasons: Sequence[str] | None = None,
    *,
    tombstone_count: int = 0,
    stop_retention_risk_count: int = 0,
) -> RetentionGuardianDryRunValidation:
    return RetentionGuardianDryRunValidation(
        valid=valid,
        reason=reason,
        reasons=tuple(reasons or (reason,)),
        tombstone_count=tombstone_count,
        stop_retention_risk_count=stop_retention_risk_count,
    )


def _tombstone_count(artifacts: Sequence[Any]) -> int:
    return sum(
        1
        for row in artifacts
        if isinstance(row, Mapping)
        and row.get("retention_state") == STATE_TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY
    )


def _stop_count(artifacts: Sequence[Any]) -> int:
    return sum(
        1
        for row in artifacts
        if isinstance(row, Mapping) and STOP_RETENTION_RISK in _list(row.get("blockers"))
    )


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
