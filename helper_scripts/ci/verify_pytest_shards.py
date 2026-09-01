#!/usr/bin/env python3
"""Verify exact cross-worker evidence for governance pytest shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any


EVIDENCE_SCHEMA = "governance_pytest_shard_evidence_v1"
ARTIFACT_PREFIX = "governance-pytest-shard-"
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
MAX_NODEID_BYTES = 8192
SOURCE_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
MANIFEST_SHA_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
EVIDENCE_FIELDS = {
    "schema_version",
    "source_sha",
    "shard_index",
    "shard_count",
    "minimum_count",
    "full_count",
    "selected_count",
    "full_manifest_sha256",
    "selected_manifest_sha256",
    "selected_nodeids",
}


class ShardEvidenceError(ValueError):
    """One or more shard artifacts violate the evidence contract."""


def _fail(message: str) -> None:
    raise ShardEvidenceError(message)


def _require_integer(name: str, value: object) -> int:
    if type(value) is not int:
        _fail(f"{name} must be an integer (bool is not accepted)")
    return value


def _manifest(nodeids: list[str]) -> str:
    payload = b"\n".join(nodeid.encode("utf-8") for nodeid in nodeids)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_payload(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        _fail(f"cannot stat evidence file {path}: {exc}")
    if size <= 0 or size > MAX_EVIDENCE_BYTES:
        _fail(f"evidence file violates size cap: {path} ({size} bytes)")
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="strict")
        payload = json.loads(text, object_pairs_hook=_unique_object)
    except ShardEvidenceError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        _fail(f"invalid UTF-8 JSON evidence file {path}: {exc}")
    if not isinstance(payload, dict):
        _fail(f"evidence payload must be an object: {path}")
    return payload


def _artifact_paths(root: Path, expected_count: int) -> list[Path]:
    if root.is_symlink():
        _fail(f"artifact root must not be a symlink: {root}")
    if not root.is_dir():
        _fail(f"artifact root is not a directory: {root}")
    expected_names = {
        f"{ARTIFACT_PREFIX}{index}" for index in range(expected_count)
    }
    try:
        root_entries = list(os.scandir(root))
    except OSError as exc:
        _fail(f"cannot enumerate artifact root {root}: {exc}")
    actual_names = {entry.name for entry in root_entries}
    if len(root_entries) != expected_count or actual_names != expected_names:
        _fail(
            "artifact root must contain exactly the preserved shard directories "
            f"{sorted(expected_names)}; found {sorted(actual_names)}"
        )

    paths: list[Path] = []
    for index in range(expected_count):
        directory = root / f"{ARTIFACT_PREFIX}{index}"
        if directory.is_symlink():
            _fail(f"artifact directory must not be a symlink: {directory}")
        if not directory.is_dir():
            _fail(f"artifact entry is not a directory: {directory}")
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            _fail(f"cannot enumerate artifact directory {directory}: {exc}")
        expected_file = f"{ARTIFACT_PREFIX}{index}.json"
        if len(entries) != 1 or entries[0].name != expected_file:
            _fail(
                f"artifact directory {directory.name} must contain exactly "
                f"{expected_file} and no recursive or extra entries"
            )
        entry = entries[0]
        if entry.is_symlink():
            _fail(f"evidence file must not be a symlink: {entry.path}")
        if not entry.is_file(follow_symlinks=False):
            _fail(f"evidence entry is not a regular file: {entry.path}")
        paths.append(Path(entry.path))
    return paths


def _validate_nodeid(nodeid: object, *, artifact_index: int) -> str:
    if not isinstance(nodeid, str):
        _fail(f"selected_nodeids[{artifact_index}] contains a non-string")
    if any(character in nodeid for character in ("\0", "\r", "\n")):
        _fail(f"selected_nodeids[{artifact_index}] contains a control character")
    try:
        encoded = nodeid.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ShardEvidenceError(
            f"selected_nodeids[{artifact_index}] contains invalid UTF-8"
        ) from exc
    if len(encoded) > MAX_NODEID_BYTES:
        _fail(f"selected nodeid exceeds the {MAX_NODEID_BYTES}-byte size cap")
    if not nodeid.startswith("tests/"):
        _fail("selected nodeid must start with tests/")
    path, separator, test_name = nodeid.partition("::")
    if not separator or not path.endswith(".py") or not test_name:
        _fail("selected nodeid must identify a test")
    return nodeid


def _validate_payload(
    payload: dict[str, Any],
    *,
    directory_index: int,
    expected_source_sha: str,
    expected_shard_count: int,
    expected_minimum_count: int,
) -> dict[str, Any]:
    if set(payload) != EVIDENCE_FIELDS:
        _fail(
            f"shard {directory_index} payload must contain exact fields; "
            f"found {sorted(payload)}"
        )
    if payload["schema_version"] != EVIDENCE_SCHEMA:
        _fail(f"shard {directory_index} has an invalid evidence schema")
    source_sha = payload["source_sha"]
    if not isinstance(source_sha, str) or SOURCE_SHA_PATTERN.fullmatch(source_sha) is None:
        _fail(f"shard {directory_index} has an invalid source SHA")
    if source_sha != expected_source_sha:
        _fail(f"shard {directory_index} does not bind the expected source SHA")

    shard_index = _require_integer("shard_index", payload["shard_index"])
    shard_count = _require_integer("shard_count", payload["shard_count"])
    minimum_count = _require_integer("minimum_count", payload["minimum_count"])
    full_count = _require_integer("full_count", payload["full_count"])
    selected_count = _require_integer("selected_count", payload["selected_count"])
    if shard_index != directory_index:
        _fail(f"shard artifact name/index mismatch at directory {directory_index}")
    if shard_count != expected_shard_count:
        _fail(f"shard {directory_index} does not bind the expected shard count")
    if minimum_count != expected_minimum_count:
        _fail(f"shard {directory_index} does not bind the expected minimum count")
    if full_count < minimum_count or full_count <= 0:
        _fail(f"shard {directory_index} full count is below the bound minimum")
    if selected_count <= 0:
        _fail(f"shard {directory_index} selected count must be positive")

    for field in ("full_manifest_sha256", "selected_manifest_sha256"):
        value = payload[field]
        if not isinstance(value, str) or MANIFEST_SHA_PATTERN.fullmatch(value) is None:
            _fail(f"shard {directory_index} has an invalid manifest SHA in {field}")

    raw_nodeids = payload["selected_nodeids"]
    if not isinstance(raw_nodeids, list):
        _fail(f"shard {directory_index} selected_nodeids must be a list")
    selected = [
        _validate_nodeid(nodeid, artifact_index=directory_index)
        for nodeid in raw_nodeids
    ]
    canonical = sorted(selected, key=lambda nodeid: nodeid.encode("utf-8"))
    if selected != canonical or len(set(selected)) != len(selected):
        _fail(f"shard {directory_index} selected_nodeids must be canonical and unique")
    if selected_count != len(selected):
        _fail(f"shard {directory_index} local selected count mismatch")
    if payload["selected_manifest_sha256"] != _manifest(selected):
        _fail(f"shard {directory_index} local selected manifest mismatch")
    return payload


def verify_shard_artifacts(
    artifacts_root: str | Path,
    *,
    expected_source_sha: str,
    expected_shard_count: int,
    expected_minimum_count: int,
) -> dict[str, object]:
    """Validate the complete preserved directory set and deterministic partition."""

    if not isinstance(expected_source_sha, str) or SOURCE_SHA_PATTERN.fullmatch(expected_source_sha) is None:
        _fail("expected source SHA must be 40 lowercase hex characters")
    expected_shard_count = _require_integer(
        "expected_shard_count", expected_shard_count
    )
    expected_minimum_count = _require_integer(
        "expected_minimum_count", expected_minimum_count
    )
    if expected_shard_count <= 0:
        _fail("expected shard count must be positive")
    if expected_minimum_count < 0:
        _fail("expected minimum count must be non-negative")

    paths = _artifact_paths(Path(artifacts_root), expected_shard_count)
    payloads = [
        _validate_payload(
            _read_payload(path),
            directory_index=index,
            expected_source_sha=expected_source_sha,
            expected_shard_count=expected_shard_count,
            expected_minimum_count=expected_minimum_count,
        )
        for index, path in enumerate(paths)
    ]

    full_counts = {payload["full_count"] for payload in payloads}
    if len(full_counts) != 1:
        _fail("all shard artifacts must bind one common full count")
    full_manifests = {payload["full_manifest_sha256"] for payload in payloads}
    if len(full_manifests) != 1:
        _fail("all shard artifacts must bind one common full manifest")
    full_count = next(iter(full_counts))
    full_manifest = next(iter(full_manifests))

    sizes = [payload["selected_count"] for payload in payloads]
    quotient, remainder = divmod(full_count, expected_shard_count)
    expected_sizes = [
        quotient + (1 if index < remainder else 0)
        for index in range(expected_shard_count)
    ]
    if sizes != expected_sizes:
        _fail(
            f"shard selected sizes are not balanced: expected {expected_sizes}, found {sizes}"
        )

    union: set[str] = set()
    for index, payload in enumerate(payloads):
        selected = payload["selected_nodeids"]
        overlap = union.intersection(selected)
        if overlap:
            _fail(f"shard selected lists are not disjoint at index {index}")
        union.update(selected)
    canonical_full = sorted(union, key=lambda nodeid: nodeid.encode("utf-8"))
    if len(canonical_full) != full_count:
        _fail(
            f"selected union count mismatch: expected {full_count}, found {len(canonical_full)}"
        )
    if _manifest(canonical_full) != full_manifest:
        _fail("selected union manifest does not match the common full manifest")

    for index, payload in enumerate(payloads):
        replayed = canonical_full[index::expected_shard_count]
        if payload["selected_nodeids"] != replayed:
            _fail(f"shard {index} does not match deterministic modulo replay")

    return {
        "source_sha": expected_source_sha,
        "shard_count": expected_shard_count,
        "shard_indices": [payload["shard_index"] for payload in payloads],
        "selected_counts": sizes,
        "full_count": full_count,
        "full_manifest_sha256": full_manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify governance pytest shard evidence artifacts"
    )
    parser.add_argument("--artifacts-root", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-shard-count", required=True, type=int)
    parser.add_argument("--expected-minimum-count", required=True, type=int)
    args = parser.parse_args()
    try:
        summary = verify_shard_artifacts(
            args.artifacts_root,
            expected_source_sha=args.expected_source_sha,
            expected_shard_count=args.expected_shard_count,
            expected_minimum_count=args.expected_minimum_count,
        )
    except ShardEvidenceError as exc:
        parser.exit(1, f"governance shard evidence rejected: {exc}\n")
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
