"""Fail-closed deterministic sharding for the governance pytest collection."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

import pytest


EVIDENCE_SCHEMA = "governance_pytest_shard_evidence_v1"
SOURCE_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class ShardSelection:
    """Canonical manifest evidence and the nodeids assigned to one shard."""

    full_count: int
    selected_count: int
    full_manifest_sha256: str
    selected_manifest_sha256: str
    selected_nodeids: tuple[str, ...]


def _require_integer(name: str, value: int) -> None:
    if type(value) is not int:  # bool is intentionally rejected.
        raise ValueError(f"{name} must be an integer")


def _manifest_sha256(nodeids: tuple[str, ...]) -> str:
    payload = b"\n".join(nodeid.encode("utf-8") for nodeid in nodeids)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def select_nodeids(
    nodeids: Iterable[str],
    *,
    shard_index: int,
    shard_count: int,
    minimum_count: int,
) -> ShardSelection:
    """Select one canonical modulo shard from a complete pytest collection."""

    _require_integer("shard_index", shard_index)
    _require_integer("shard_count", shard_count)
    _require_integer("minimum_count", minimum_count)
    if shard_count <= 0:
        raise ValueError("shard_count must be a positive integer")
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError("shard_index is out of range")
    if minimum_count < 0:
        raise ValueError("minimum_count must be a non-negative integer")

    validated: list[str] = []
    for nodeid in nodeids:
        if not isinstance(nodeid, str):
            raise ValueError("every nodeid must be a string")
        if any(character in nodeid for character in ("\0", "\r", "\n")):
            raise ValueError("nodeid contains a control character")
        try:
            nodeid.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("nodeid must be valid UTF-8") from exc
        if not nodeid.startswith("tests/"):
            raise ValueError("nodeid must start with tests/")
        path, separator, test_name = nodeid.partition("::")
        if not separator or not path.endswith(".py") or not test_name:
            raise ValueError("nodeid must identify a test")
        validated.append(nodeid)

    if not validated:
        raise ValueError("complete nodeid collection must not be empty")
    if len(validated) < minimum_count:
        raise ValueError(
            f"complete nodeid count {len(validated)} is below minimum {minimum_count}"
        )
    if len(set(validated)) != len(validated):
        raise ValueError("complete nodeid collection contains a duplicate")

    canonical = tuple(sorted(validated, key=lambda nodeid: nodeid.encode("utf-8")))
    selected = tuple(
        nodeid
        for position, nodeid in enumerate(canonical)
        if position % shard_count == shard_index
    )
    if not selected:
        raise ValueError("selected shard is empty")

    return ShardSelection(
        full_count=len(canonical),
        selected_count=len(selected),
        full_manifest_sha256=_manifest_sha256(canonical),
        selected_manifest_sha256=_manifest_sha256(selected),
        selected_nodeids=selected,
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("governance-sharding")
    group.addoption("--governance-shard-index", type=int, default=None)
    group.addoption("--governance-shard-count", type=int, default=None)
    group.addoption("--governance-shard-minimum", type=int, default=None)
    group.addoption("--governance-shard-evidence-path", default=None)
    group.addoption("--governance-shard-source-sha", default=None)


def _evidence_binding(config: pytest.Config) -> tuple[Path, str] | None:
    evidence_path = config.getoption("governance_shard_evidence_path")
    source_sha = config.getoption("governance_shard_source_sha")
    if evidence_path is None and source_sha is None:
        return None
    if not isinstance(evidence_path, str) or not evidence_path:
        raise pytest.UsageError(
            "governance shard evidence path and source SHA are required together"
        )
    if not isinstance(source_sha, str) or SOURCE_SHA_PATTERN.fullmatch(source_sha) is None:
        raise pytest.UsageError(
            "governance shard evidence source SHA must be 40 lowercase hex characters"
        )
    return Path(evidence_path), source_sha


def _write_evidence(
    path: Path,
    *,
    source_sha: str,
    shard_index: int,
    shard_count: int,
    minimum_count: int,
    selection: ShardSelection,
) -> None:
    evidence = {
        "schema_version": EVIDENCE_SCHEMA,
        "source_sha": source_sha,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "minimum_count": minimum_count,
        "full_count": selection.full_count,
        "selected_count": selection.selected_count,
        "full_manifest_sha256": selection.full_manifest_sha256,
        "selected_manifest_sha256": selection.selected_manifest_sha256,
        "selected_nodeids": list(selection.selected_nodeids),
    }
    serialized = json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as evidence_file:
            evidence_file.write(serialized)
    except FileExistsError as exc:
        raise pytest.UsageError(
            f"governance shard evidence path already exists: {path}"
        ) from exc
    except OSError as exc:
        raise pytest.UsageError(
            f"governance shard evidence could not be created: {path}: {exc}"
        ) from exc


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    values = {
        "shard_index": config.getoption("governance_shard_index"),
        "shard_count": config.getoption("governance_shard_count"),
        "minimum_count": config.getoption("governance_shard_minimum"),
    }
    evidence_binding = _evidence_binding(config)
    if all(value is None for value in values.values()):
        if evidence_binding is not None:
            raise pytest.UsageError(
                "all governance shard options are required with shard evidence"
            )
        return
    if any(value is None for value in values.values()):
        raise pytest.UsageError("all governance shard options are required together")

    try:
        selection = select_nodeids(
            (item.nodeid for item in items),
            shard_index=values["shard_index"],
            shard_count=values["shard_count"],
            minimum_count=values["minimum_count"],
        )
    except ValueError as exc:
        raise pytest.UsageError(f"governance shard selection rejected: {exc}") from exc

    if evidence_binding is not None:
        evidence_path, source_sha = evidence_binding
        _write_evidence(
            evidence_path,
            source_sha=source_sha,
            shard_index=values["shard_index"],
            shard_count=values["shard_count"],
            minimum_count=values["minimum_count"],
            selection=selection,
        )

    selected = set(selection.selected_nodeids)
    items[:] = [item for item in items if item.nodeid in selected]
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(
            "governance shard "
            f"{values['shard_index']}/{values['shard_count']}: "
            f"full_count={selection.full_count} "
            f"full_manifest={selection.full_manifest_sha256} "
            f"selected_count={selection.selected_count} "
            f"selected_manifest={selection.selected_manifest_sha256}"
        )
