"""Before/after repository generation receipts for task-owned mutations."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_governance_capture import (
    LOCAL_REPRODUCIBLE,
    REPO_ROOT,
    capture_native_linear_commit_range,
    capture_repository,
    repository_generation_digest,
    validate_repository_capture,
)
from agent_governance_registry import load_registry


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$")
FIELDS = {
    "schema_version", "trust_tier", "task_contract_digest", "node_id",
    "role_id", "scope", "before", "after", "before_generation_digest",
    "after_generation_digest", "owned_before", "owned_after",
    "owned_before_generation_digest", "owned_after_generation_digest",
    "mutation_observed", "affected_paths", "record_digest",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _record_digest(record: dict[str, Any]) -> str:
    return _digest({key: value for key, value in record.items() if key != "record_digest"})


def _time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _repository_capture_is_clean(capture: Any) -> bool:
    return (
        isinstance(capture, dict)
        and capture.get("tracked_paths") == []
        and capture.get("untracked") == []
        and capture.get("changed_paths") == []
        and isinstance(capture.get("tracked_diff"), dict)
        and capture["tracked_diff"].get("bytes") == 0
    )


def capture_repository_change(
    *,
    before: dict[str, Any],
    task_contract_digest: str,
    node_id: str,
    role_id: str,
    scope: list[str],
    owned_before: dict[str, Any] | None = None,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Capture one owned mutation inside a chain-wide repository generation."""

    before_errors = validate_repository_capture(
        before, root=root, require_current=False
    )
    if before_errors:
        raise ValueError("invalid before repository capture: " + "; ".join(before_errors))
    generation_scope = before.get("scope", [])
    if not set(scope).issubset(set(generation_scope)):
        raise ValueError("owned scope is outside the chain generation scope")
    owned_before = before if owned_before is None else owned_before
    owned_before_errors = validate_repository_capture(
        owned_before, expected_scope=scope, root=root, require_current=False,
    )
    if owned_before_errors:
        raise ValueError(
            "invalid owned before repository capture: "
            + "; ".join(owned_before_errors)
        )
    owned_after = capture_repository(scope, root=root)
    after = capture_repository(generation_scope, root=root)
    before_generation = repository_generation_digest(before)
    after_generation = repository_generation_digest(after)
    owned_before_generation = repository_generation_digest(owned_before)
    owned_after_generation = repository_generation_digest(owned_after)
    record: dict[str, Any] = {
        "schema_version": "repository_change_record_v1",
        "trust_tier": LOCAL_REPRODUCIBLE,
        "task_contract_digest": task_contract_digest,
        "node_id": node_id,
        "role_id": role_id,
        "scope": sorted(scope),
        "before": before,
        "after": after,
        "before_generation_digest": before_generation,
        "after_generation_digest": after_generation,
        "owned_before": owned_before,
        "owned_after": owned_after,
        "owned_before_generation_digest": owned_before_generation,
        "owned_after_generation_digest": owned_after_generation,
        "mutation_observed": owned_before_generation != owned_after_generation,
        "affected_paths": sorted(
            set(owned_before.get("changed_paths", []))
            | set(owned_after.get("changed_paths", []))
        ),
    }
    record["record_digest"] = _record_digest(record)
    errors = validate_repository_change_record(
        record,
        expected_task_contract_digest=task_contract_digest,
        expected_node_id=node_id,
        expected_role_id=role_id,
        expected_scope=scope,
        root=root,
        require_after_current=True,
    )
    if errors:
        raise ValueError("invalid repository change record: " + "; ".join(errors))
    return record


def validate_repository_change_record(
    record: Any,
    *,
    expected_task_contract_digest: str | None = None,
    expected_node_id: str | None = None,
    expected_role_id: str | None = None,
    expected_scope: list[str] | None = None,
    expected_source_head: str | None = None,
    root: Path = REPO_ROOT,
    require_after_current: bool = False,
) -> list[str]:
    if not isinstance(record, dict):
        return ["repository change record must be an object"]
    errors: list[str] = []
    if set(record) != FIELDS:
        errors.append("repository change record fields do not match contract")
    if record.get("schema_version") != "repository_change_record_v1":
        errors.append("repository change record schema_version is invalid")
    if record.get("trust_tier") != LOCAL_REPRODUCIBLE:
        errors.append("repository change record trust tier is invalid")
    if not DIGEST_RE.fullmatch(str(record.get("task_contract_digest", ""))):
        errors.append("repository change task_contract_digest is invalid")
    for field in ("node_id", "role_id"):
        if not isinstance(record.get(field), str) or not IDENTIFIER_RE.fullmatch(record[field]):
            errors.append(f"repository change {field} is invalid")
    if record.get("role_id") not in load_registry()["roles"]:
        errors.append("repository change role_id is not registered")
    scope = record.get("scope")
    if not isinstance(scope, list) or not scope or scope != sorted(set(scope)):
        errors.append("repository change scope must be sorted, unique, and non-empty")
        scope = []
    before = record.get("before")
    generation_scope = before.get("scope") if isinstance(before, dict) else None
    if (
        not isinstance(generation_scope, list)
        or not set(scope).issubset(set(generation_scope))
    ):
        errors.append("repository change generation scope does not cover owned scope")
        generation_scope = None
    for field, capture_scope in (
        ("before", generation_scope), ("after", generation_scope),
        ("owned_before", scope or None), ("owned_after", scope or None),
    ):
        errors.extend(
            f"repository change {field.replace('_', ' ')}: {error}"
            for error in validate_repository_capture(
                record.get(field), expected_scope=capture_scope, root=root,
                require_current=require_after_current and field in {"after", "owned_after"},
            )
        )
    after = record.get("after")
    owned_before = record.get("owned_before")
    owned_after = record.get("owned_after")
    if all(isinstance(item, dict) for item in (before, after, owned_before, owned_after)):
        before_generation = repository_generation_digest(before)
        after_generation = repository_generation_digest(after)
        owned_before_generation = repository_generation_digest(owned_before)
        owned_after_generation = repository_generation_digest(owned_after)
        if record.get("before_generation_digest") != before_generation:
            errors.append("repository change before generation digest is invalid")
        if record.get("after_generation_digest") != after_generation:
            errors.append("repository change after generation digest is invalid")
        if record.get("owned_before_generation_digest") != owned_before_generation:
            errors.append("repository change owned before generation digest is invalid")
        if record.get("owned_after_generation_digest") != owned_after_generation:
            errors.append("repository change owned after generation digest is invalid")
        owned_mutation = owned_before_generation != owned_after_generation
        if record.get("mutation_observed") is not owned_mutation:
            errors.append("repository change mutation_observed is inconsistent")
        if (before_generation != after_generation) is not owned_mutation:
            errors.append(
                "repository change chain generation does not match owned mutation"
            )
        affected = sorted(
            set(owned_before.get("changed_paths", []))
            | set(owned_after.get("changed_paths", []))
        )
        if record.get("affected_paths") != affected:
            errors.append("repository change affected_paths are inconsistent")
        captures = (before, owned_before, owned_after, after)
        if expected_source_head is not None and any(
            capture.get("source_head") != expected_source_head
            for capture in captures
        ):
            errors.append("repository change source head differs from admitted baseline")
        times = [_time(capture.get("observed_at")) for capture in captures]
        if any(value is None for value in times) or times != sorted(times):
            errors.append("repository change observation interval is invalid")
    for field, expected in (
        ("task_contract_digest", expected_task_contract_digest),
        ("node_id", expected_node_id),
        ("role_id", expected_role_id),
    ):
        if expected is not None and record.get(field) != expected:
            errors.append(f"repository change does not match expected {field}")
    if expected_scope is not None and record.get("scope") != sorted(expected_scope):
        errors.append("repository change does not match expected scope")
    try:
        expected_digest = _record_digest(record)
    except (TypeError, ValueError):
        expected_digest = None
        errors.append("repository change record is not canonical JSON")
    if record.get("record_digest") != expected_digest:
        errors.append("repository change record self-digest is invalid")
    return errors


def writer_scope_contracts(
    nodes: Any,
    *,
    expected_dirty_scope: list[str],
    scope_contract: Any = None,
    adaptive_writer_node_ids: set[str] | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Validate and return ordered effective writer ownership."""

    if not isinstance(nodes, list):
        return {}, ["dispatch writer nodes must be an array"]
    dirty_scope = sorted(expected_dirty_scope)
    dirty_set = set(dirty_scope)
    raw_writers: dict[str, list[str]] = {}
    errors: list[str] = []
    node_by_id = {
        node.get("node_id"): node for node in nodes
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
    dependency_cache: dict[str, set[str]] = {}

    def dependencies(node_id: str, resolving: set[str] | None = None) -> set[str]:
        if node_id in dependency_cache:
            return dependency_cache[node_id]
        resolving = set() if resolving is None else resolving
        if node_id in resolving:
            return set()
        direct = node_by_id.get(node_id, {}).get("requires", [])
        result = set(direct) if isinstance(direct, list) else set()
        for required in list(result):
            result.update(dependencies(required, resolving | {node_id}))
        dependency_cache[node_id] = result
        return result
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        node_id = node.get("node_id")
        path_scope = node.get("path_scope")
        if (
            not isinstance(path_scope, list)
            or path_scope != sorted(set(path_scope))
            or any(not isinstance(path, str) or not path for path in path_scope)
        ):
            errors.append(f"dispatch node {node_id or index} path_scope is invalid")
            continue
        if not set(path_scope).issubset(dirty_set):
            errors.append(f"dispatch node {node_id} path_scope exceeds task dirty_scope")
        if node.get("node_class") != "work":
            if path_scope:
                errors.append(f"verification node {node_id} cannot own repository paths")
            continue
        if not path_scope and dirty_scope:
            errors.append(f"writer node {node_id} has no owned path scope")
            continue
        if isinstance(node_id, str) and node_id:
            raw_writers[node_id] = path_scope
    if scope_contract is None:
        writers = raw_writers
    else:
        writers: dict[str, list[str]] = {}
        if (
            not isinstance(scope_contract, dict)
            or set(scope_contract) != {"schema_version", "writers"}
            or scope_contract.get("schema_version")
            != "repository_writer_scope_contract_v1"
            or not isinstance(scope_contract.get("writers"), list)
        ):
            errors.append("repository writer scope claim contract is invalid")
            contract_writers: list[Any] = []
        else:
            contract_writers = scope_contract["writers"]
        raw_ids = list(raw_writers)
        contract_ids: list[Any] = []
        for index, writer in enumerate(contract_writers):
            if not isinstance(writer, dict) or set(writer) != {
                "node_id", "role", "path_scope",
            }:
                errors.append(
                    f"repository writer scope claim writers[{index}] is invalid"
                )
                continue
            node_id = writer.get("node_id")
            contract_ids.append(node_id)
            node = node_by_id.get(node_id)
            if (
                not isinstance(node_id, str)
                or node_id not in raw_writers
                or node is None
                or writer.get("role") != node.get("role")
            ):
                errors.append(
                    "repository writer scope claim role/node differs from dispatch"
                )
            effective_scope = writer.get("path_scope")
            if (
                not isinstance(effective_scope, list)
                or not effective_scope
                or effective_scope != sorted(set(effective_scope))
                or any(not isinstance(path, str) or not path for path in effective_scope)
                or not set(effective_scope).issubset(dirty_set)
            ):
                errors.append(
                    f"repository effective writer {node_id or index} scope is invalid or empty"
                )
                continue
            if isinstance(node_id, str) and node_id:
                writers[node_id] = effective_scope
        if contract_ids != raw_ids:
            errors.append(
                "repository writer scope claim writer order differs from dispatch"
            )

        adaptive_ids = adaptive_writer_node_ids or set()
        raw_claimants: dict[str, list[str]] = {
            path: [node_id for node_id, scope in raw_writers.items() if path in scope]
            for path in dirty_scope
        }
        effective_claimants: dict[str, list[str]] = {
            path: [node_id for node_id, scope in writers.items() if path in scope]
            for path in dirty_scope
        }
        for path in dirty_scope:
            raw = raw_claimants[path]
            effective = effective_claimants[path]
            if len(effective) != 1:
                errors.append(
                    f"repository dirty path has multiple or missing terminal claimant: {path}"
                )
                continue
            if len(raw) == 1:
                if effective != raw:
                    errors.append(
                        f"repository writer scope claim transfers unclaimed path: {path}"
                    )
                continue
            if len(raw) != 2:
                errors.append(
                    f"repository dirty path has multiple terminal writer claimants: {path}"
                )
                continue
            prior, terminal = raw
            if node_by_id.get(prior, {}).get("role") != node_by_id.get(
                terminal, {}
            ).get("role"):
                errors.append(
                    f"repository path transfer writer roles differ: {path}"
                )
            if node_by_id.get(prior, {}).get("permission") != node_by_id.get(
                terminal, {}
            ).get("permission"):
                errors.append(
                    f"repository path transfer writer permissions differ: {path}"
                )
            if terminal not in adaptive_ids:
                errors.append(
                    f"repository path transfer targets non-adaptive writer: {path}"
                )
            if prior not in dependencies(terminal):
                errors.append(
                    f"repository adaptive writer transfer is not transitively serialized: {path}"
                )
            if effective != [terminal]:
                errors.append(
                    f"repository transferred path terminal claimant is invalid: {path}"
                )

        raw_paths = [
            (node_id, path) for node_id, scope in raw_writers.items() for path in scope
        ]
        for index, (left_node, left_path) in enumerate(raw_paths):
            for right_node, right_path in raw_paths[index + 1:]:
                if left_node == right_node or left_path == right_path:
                    continue
                if (
                    left_path.startswith(right_path.rstrip("/") + "/")
                    or right_path.startswith(left_path.rstrip("/") + "/")
                ):
                    errors.append(
                        "dispatch raw writer scopes have non-literal prefix overlap: "
                        f"{left_node}:{left_path} and {right_node}:{right_path}"
                    )
    owned_paths = [
        (node_id, path) for node_id, scope in writers.items() for path in scope
    ]
    for index, (left_node, left_path) in enumerate(owned_paths):
        for right_node, right_path in owned_paths[index + 1:]:
            if left_node == right_node:
                continue
            if (
                left_path == right_path
                or left_path.startswith(right_path.rstrip("/") + "/")
                or right_path.startswith(left_path.rstrip("/") + "/")
            ):
                errors.append(
                    f"dispatch writer path scopes overlap: {left_node}:{left_path} and {right_node}:{right_path}"
                )
    owned = {path for scope in writers.values() for path in scope}
    if writers and dirty_scope and owned != dirty_set:
        errors.append("dispatch writer path scopes do not cover task dirty_scope exactly")
    writer_ids = list(writers)
    for index, node_id in enumerate(writer_ids[1:], 1):
        if writer_ids[index - 1] not in dependencies(node_id):
            errors.append(
                "dispatch writer work nodes must be transitively serialized in "
                "canonical order"
            )
    return writers, errors


def validate_repository_change_chain(
    records: Any,
    *,
    expected_writer_scopes: dict[str, list[str]],
    expected_writer_roles: dict[str, str] | None = None,
    expected_source_head: str | None = None,
    root: Path = REPO_ROOT,
    require_final_current: bool = True,
) -> list[str]:
    """Validate exact, ordered, node-owned writer mutation coverage."""

    if not isinstance(records, list) or not records:
        return ["repository change chain must contain at least one ordered record"]
    errors: list[str] = []
    if not isinstance(expected_writer_scopes, dict) or not expected_writer_scopes:
        return ["repository change chain expected writer scopes are missing"]
    expected_nodes = list(expected_writer_scopes)
    for node_id, scope in expected_writer_scopes.items():
        if (
            not isinstance(node_id, str) or not node_id
            or not isinstance(scope, list) or not scope
            or scope != sorted(set(scope))
            or any(not isinstance(path, str) or not path for path in scope)
        ):
            errors.append(f"repository writer {node_id} path scope is invalid")
    owned_paths = [
        (node_id, path)
        for node_id, scope in expected_writer_scopes.items()
        for path in scope
    ]
    for index, (left_node, left_path) in enumerate(owned_paths):
        for right_node, right_path in owned_paths[index + 1:]:
            if left_node == right_node:
                continue
            if (
                left_path == right_path
                or left_path.startswith(right_path.rstrip("/") + "/")
                or right_path.startswith(left_path.rstrip("/") + "/")
            ):
                errors.append(
                    f"repository writer path scopes overlap: {left_node}:{left_path} and {right_node}:{right_path}"
                )
    actual_nodes = [
        record.get("node_id") if isinstance(record, dict) else None
        for record in records
    ]
    if set(actual_nodes) != set(expected_nodes) or len(actual_nodes) != len(expected_nodes):
        errors.append("repository change chain writer coverage differs from admitted write nodes")
    if actual_nodes != expected_nodes:
        errors.append("repository change chain writer order differs from canonical dispatch order")

    previous: dict[str, Any] | None = None
    generation_scope = sorted({path for scope in expected_writer_scopes.values() for path in scope})
    head_transitions: list[tuple[str | None, str | None]] = []
    for index, record in enumerate(records):
        node_id = record.get("node_id") if isinstance(record, dict) else None
        expected_scope = expected_writer_scopes.get(str(node_id))
        errors.extend(
            f"repository change chain[{index}] {error}"
            for error in validate_repository_change_record(
                record, expected_scope=expected_scope, root=root,
                require_after_current=False,
            )
        )
        if not isinstance(record, dict):
            continue
        if expected_scope is None:
            errors.append(
                f"repository change chain[{index}] node is not an admitted writer work node"
            )
        elif record.get("scope") != expected_scope:
            errors.append(
                f"repository change chain[{index}] does not match expected node-owned scope"
            )
        if (
            expected_writer_roles is not None
            and expected_writer_roles.get(str(node_id)) != record.get("role_id")
        ):
            errors.append(
                f"repository change chain[{index}] does not match expected writer role"
            )
        if record.get("mutation_observed") is not True:
            errors.append(f"repository change chain[{index}] records no mutation")
        before_head = (
            record.get("before", {}).get("source_head")
            if isinstance(record.get("before"), dict) else None
        )
        after_head = (
            record.get("after", {}).get("source_head")
            if isinstance(record.get("after"), dict) else None
        )
        head_transitions.append((before_head, after_head))
        if (
            not isinstance(record.get("owned_before"), dict)
            or record["owned_before"].get("source_head") != before_head
            or not isinstance(record.get("owned_after"), dict)
            or record["owned_after"].get("source_head") != after_head
        ):
            errors.append(
                f"repository change chain[{index}] task and owned endpoint heads differ"
            )
        if previous is not None:
            prior_after = _time(previous.get("after", {}).get("observed_at"))
            current_before = _time(record.get("before", {}).get("observed_at"))
            if (
                prior_after is None or current_before is None
                or current_before < prior_after
            ):
                errors.append(
                    f"repository change chain[{index}] observation order regresses"
                )
            if record.get("before_generation_digest") != previous.get(
                "after_generation_digest"
            ):
                errors.append(
                    f"repository change chain[{index}] before generation does not "
                    "equal the preceding writer after generation"
                )
            if before_head != previous.get("after", {}).get("source_head"):
                errors.append(
                    f"repository change chain[{index}] before source head does not "
                    "equal the preceding writer after source head"
                )
        if isinstance(record.get("before"), dict) and (
            record["before"].get("scope") != generation_scope
            or not isinstance(record.get("after"), dict)
            or record["after"].get("scope") != generation_scope
        ):
            errors.append(
                f"repository change chain[{index}] does not capture the exact "
                "task-wide generation scope"
            )
        previous = record

    committed = [before_head != after_head for before_head, after_head in head_transitions]
    committed_mode = bool(committed and all(committed))
    if any(committed) and not committed_mode:
        errors.append("repository change chain mixes dirty and committed writer modes")
    if committed_mode:
        first = records[0] if records else None
        first_head = (
            first.get("before", {}).get("source_head")
            if isinstance(first, dict) else None
        )
        if expected_source_head is None or first_head != expected_source_head:
            errors.append(
                "repository committed change chain does not start at admitted baseline"
            )
        aggregate_paths: set[str] = set()
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            endpoints = [
                record.get(field) for field in (
                    "before", "owned_before", "owned_after", "after",
                )
            ]
            if any(not _repository_capture_is_clean(endpoint) for endpoint in endpoints):
                errors.append(
                    f"repository committed change chain[{index}] endpoint is not clean"
                )
            before_head, after_head = head_transitions[index]
            if not isinstance(before_head, str) or not isinstance(after_head, str):
                continue
            commits, _patches, range_errors = capture_native_linear_commit_range(
                root, before_head, after_head,
            )
            errors.extend(
                f"repository committed change chain[{index}] {error}"
                for error in range_errors
            )
            expected_scope = set(
                expected_writer_scopes.get(str(record.get("node_id")), [])
            )
            for commit in commits:
                paths = commit.get("paths")
                if not isinstance(paths, list) or not paths:
                    errors.append(
                        f"repository committed change chain[{index}] contains an empty commit"
                    )
                    continue
                aggregate_paths.update(paths)
                if not set(paths).issubset(expected_scope):
                    errors.append(
                        f"repository committed change chain[{index}] commit paths exceed writer scope"
                    )
        if not aggregate_paths:
            errors.append("repository committed change chain touched no paths")
    elif expected_source_head is not None and any(
        head != expected_source_head
        for transition in head_transitions for head in transition
    ):
        errors.append("repository dirty change chain source head differs from admitted baseline")

    if require_final_current and not committed_mode:
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            node_scope = expected_writer_scopes.get(str(record.get("node_id")))
            if node_scope is None:
                continue
            errors.extend(
                f"repository change chain[{index}] writer after: {error}"
                for error in validate_repository_capture(
                    record.get("owned_after"), expected_scope=node_scope, root=root,
                    require_current=True,
                )
            )
    if require_final_current:
        final = records[-1] if records else None
        if isinstance(final, dict):
            final_scope = expected_writer_scopes.get(str(final.get("node_id")))
            if committed_mode and final_scope is not None:
                errors.extend(
                    f"repository change chain final writer: {error}"
                    for error in validate_repository_capture(
                        final.get("owned_after"), expected_scope=final_scope,
                        root=root, require_current=True,
                    )
                )
            errors.extend(
                f"repository change chain final generation: {error}"
                for error in validate_repository_capture(
                    final.get("after"), expected_scope=generation_scope, root=root,
                    require_current=True,
                )
            )
    return errors
