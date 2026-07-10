"""Bounded immutable ingress for candidate-aware R3 evidence boards.

This adapter deliberately turns source defects into structured, hash-bound
abstentions.  It never falls back to ``top_side_cells`` or a mutable latest
alias and performs no database, exchange, or runtime action.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ml_training.alr_safe_file import (
    AlrSafeFileError,
    CHANGED,
    NOT_REGULAR,
    SECURE_OPEN_UNAVAILABLE,
    SIZE_INVALID,
    read_bounded_regular_file,
)


OUTPUT_SCHEMA_VERSION = "alr_candidate_evidence_snapshot_v1"
SOURCE_SCHEMA_VERSION = "cost_gate_demo_learning_lane_blocked_outcome_review_v5"
BOARD_SCHEMA_VERSION = "cost_gate_learning_candidate_board_v1"

_IMMUTABLE_NAME_RE = re.compile(
    r"^blocked_outcome_review_(?P<stamp>[0-9]{8}T[0-9]{6}Z)\.json$"
)
_SOURCE_PREFIX = "blocked_outcome_review_"
_LATEST_NAME = "blocked_outcome_review_latest.json"


def load_candidate_evidence_snapshot(
    explicit_directory: str | Path,
    *,
    evaluated_at: str,
    max_age_seconds: int,
    max_files: int,
    max_bytes: int,
) -> dict[str, Any]:
    """Load the newest complete immutable board within explicit bounds.

    Missing, stale, malformed, raced, or incomplete evidence is a normal
    fail-closed result.  Invalid caller policy is a programming error and is
    rejected before any filesystem access.
    """
    evaluated = _parse_utc(evaluated_at, "evaluated_at_invalid")
    _positive_int(max_age_seconds, "max_age_seconds_invalid")
    _positive_int(max_files, "max_files_invalid")
    _positive_int(max_bytes, "max_bytes_invalid")
    canonical_evaluated_at = _utc_z(evaluated)
    root = Path(explicit_directory).expanduser()

    try:
        root_metadata = root.lstat()
    except FileNotFoundError:
        return _failure("DIRECTORY_MISSING", canonical_evaluated_at)
    except OSError:
        return _failure("DIRECTORY_IO_ERROR", canonical_evaluated_at)
    if stat.S_ISLNK(root_metadata.st_mode):
        return _failure("PATH_SYMLINK", canonical_evaluated_at)
    if not stat.S_ISDIR(root_metadata.st_mode):
        return _failure("PATH_NOT_DIRECTORY", canonical_evaluated_at)

    immutable: list[tuple[str, Path, os.stat_result]] = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:
        return _failure("DIRECTORY_IO_ERROR", canonical_evaluated_at)
    for entry in entries:
        name = entry.name
        if name == _LATEST_NAME:
            return _failure("LATEST_ALIAS_PRESENT", canonical_evaluated_at)
        match = _IMMUTABLE_NAME_RE.fullmatch(name)
        if name.startswith(_SOURCE_PREFIX) and match is None:
            return _failure("UNSAFE_FILE_PRESENT", canonical_evaluated_at)
        if match is None:
            continue
        try:
            metadata = entry.lstat()
        except OSError:
            return _failure("SOURCE_IO_ERROR", canonical_evaluated_at)
        if stat.S_ISLNK(metadata.st_mode):
            return _failure("SOURCE_SYMLINK", canonical_evaluated_at)
        if not stat.S_ISREG(metadata.st_mode):
            return _failure("SOURCE_NOT_REGULAR", canonical_evaluated_at)
        immutable.append((match.group("stamp"), entry, metadata))

    if not immutable:
        return _failure("NO_IMMUTABLE_SNAPSHOT", canonical_evaluated_at)
    total_bytes = sum(item[2].st_size for item in immutable)
    if len(immutable) > max_files or total_bytes > max_bytes:
        return _failure(
            "UNIVERSE_TRUNCATED",
            canonical_evaluated_at,
            source_file_count=len(immutable),
            source_total_bytes=total_bytes,
        )

    _, selected_path, selected_metadata = immutable[-1]
    try:
        raw = read_bounded_regular_file(
            selected_path,
            max_bytes=max_bytes,
            require_nonempty=False,
            require_private_mode=False,
            expected_stat=selected_metadata,
        )
    except AlrSafeFileError as exc:
        status = {
            CHANGED: "SOURCE_CHANGED_DURING_READ",
            NOT_REGULAR: "SOURCE_NOT_REGULAR",
            SIZE_INVALID: "UNIVERSE_TRUNCATED",
            SECURE_OPEN_UNAVAILABLE: "SOURCE_SECURE_OPEN_UNAVAILABLE",
        }.get(exc.code, "SOURCE_IO_ERROR")
        return _failure(status, canonical_evaluated_at)

    content_hash = hashlib.sha256(raw).hexdigest()
    def reject_non_finite(value: str) -> None:
        raise ValueError(f"non_finite_json_constant:{value}")

    try:
        payload = json.loads(raw, parse_constant=reject_non_finite)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return _failure(
            "SOURCE_JSON_INVALID",
            canonical_evaluated_at,
            source_content_sha256=content_hash,
        )
    if not isinstance(payload, Mapping):
        return _failure("SOURCE_NOT_MAPPING", canonical_evaluated_at)
    if payload.get("schema_version") != SOURCE_SCHEMA_VERSION:
        return _failure("SOURCE_SCHEMA_INVALID", canonical_evaluated_at)

    generated_raw = payload.get("generated_at_utc")
    try:
        generated = _parse_utc(generated_raw, "SOURCE_GENERATED_AT_INVALID")
    except ValueError:
        return _failure("SOURCE_GENERATED_AT_INVALID", canonical_evaluated_at)
    age_seconds = (evaluated - generated).total_seconds()
    if age_seconds < 0:
        return _failure("SOURCE_FROM_FUTURE", canonical_evaluated_at)
    if age_seconds > max_age_seconds:
        return _failure("SOURCE_STALE", canonical_evaluated_at)

    board = payload.get("learning_candidate_board")
    if not isinstance(board, Mapping):
        return _failure("LEARNING_BOARD_MISSING", canonical_evaluated_at)
    if board.get("schema_version") != BOARD_SCHEMA_VERSION:
        return _failure("LEARNING_BOARD_SCHEMA_INVALID", canonical_evaluated_at)
    if board.get("candidate_universe_complete") is not True:
        return _failure("CANDIDATE_UNIVERSE_INCOMPLETE", canonical_evaluated_at)
    declared_board_hash = board.get("board_hash")
    if not _is_sha256(declared_board_hash):
        return _failure("BOARD_HASH_INVALID", canonical_evaluated_at)
    board_without_hash = {
        str(key): copy.deepcopy(value)
        for key, value in board.items()
        if key != "board_hash"
    }
    if declared_board_hash != _canonical_sha256(board_without_hash):
        return _failure("BOARD_HASH_MISMATCH", canonical_evaluated_at)
    candidate_rows_raw = board.get("candidate_rows")
    if not isinstance(candidate_rows_raw, list) or not all(
        isinstance(row, Mapping) for row in candidate_rows_raw
    ):
        return _failure("CANDIDATE_ROWS_INVALID", canonical_evaluated_at)
    candidate_rows = sorted(
        (copy.deepcopy(dict(row)) for row in candidate_rows_raw),
        key=_candidate_sort_key,
    )
    candidate_set_hash = _canonical_sha256(candidate_rows)

    result: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "source_status": "READY",
        "evaluated_at": canonical_evaluated_at,
        "generated_at": _utc_z(generated),
        "source_file": os.path.abspath(selected_path),
        "source_file_count": len(immutable),
        "source_total_bytes": total_bytes,
        "source_content_sha256": content_hash,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "board_schema_version": BOARD_SCHEMA_VERSION,
        "board_hash": declared_board_hash,
        "candidate_set_hash": candidate_set_hash,
        "candidate_universe_complete": True,
        "candidate_rows": candidate_rows,
        "selection_allowed": True,
        "latest_alias_used": False,
    }
    result["snapshot_hash"] = _canonical_sha256(result)
    return result


def _failure(
    status: str,
    evaluated_at: str,
    **details: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "source_status": status,
        "evaluated_at": evaluated_at,
        "candidate_universe_complete": False,
        "candidate_rows": [],
        "selection_allowed": False,
        "latest_alias_used": False,
        **details,
    }
    result["snapshot_hash"] = _canonical_sha256(result)
    return result


def _candidate_sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    candidate_id = row.get("candidate_id")
    return (
        candidate_id if isinstance(candidate_id, str) else "",
        _canonical_sha256(row),
    )


def _canonical_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical_json_invalid") from exc
    return hashlib.sha256(encoded).hexdigest()


def _parse_utc(value: Any, reason: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(reason)
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(reason) from exc
    if parsed.tzinfo is None:
        raise ValueError(reason)
    return parsed.astimezone(timezone.utc)


def _utc_z(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    if normalized.microsecond:
        return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def _positive_int(value: Any, reason: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(reason)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))
