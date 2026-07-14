"""
MODULE_NOTE
模塊用途：把完整 R3 candidate board 發布到 ALR consumer 的專用 immutable rendezvous。
主要函數：publish_candidate_board。
依賴：Python 標準庫及 candidate_board v2 純驗證接口。
硬邊界：只接受 stamped v6/board-v2；目的端永不建立 latest alias，也不覆寫同名 artifact。
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
for _path in (str(RESEARCH_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cost_gate_learning_lane.candidate_board import (
    candidate_cost_evidence_v2,
    candidate_cost_projection_for_recorded_date,
    validate_learning_candidate_board_v2,
)
from cost_gate_learning_lane.cost_model import QUANTILE_ARTIFACT_MAX_AGE_HOURS
from cost_gate_learning_lane.outcome_review import _load_expected_slippage


SOURCE_SCHEMA_VERSION = "cost_gate_demo_learning_lane_blocked_outcome_review_v6"
BOARD_SCHEMA_VERSION = "cost_gate_learning_candidate_board_v2"
_STAMPED_NAME_RE = re.compile(
    r"^blocked_outcome_review_(?P<stamp>[0-9]{8}T[0-9]{6}Z)\.json$"
)
_MAX_SOURCE_BYTES = 16 * 1024 * 1024
_MAX_SLIPPAGE_ARTIFACT_BYTES = 16 * 1024 * 1024
_CONSUMER_MAX_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_FUTURE_SKEW_SECONDS = 5
_LOCK_FILE_NAME = ".alr-candidate-board.lock"


class CandidateBoardPublishError(ValueError):
    """目的端不安全或 artifact 不符合 immutable rendezvous contract。"""


def publish_candidate_board(
    source_path: str | Path,
    destination_directory: str | Path,
    *,
    retention_limit: int,
    slippage_artifact_path: str | Path | None = None,
    max_total_bytes: int = _CONSUMER_MAX_TOTAL_BYTES,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """原子發布一份完整 board；同名目的檔存在時絕不覆寫。"""
    source = Path(source_path)
    source_stamp = _filename_stamp(
        source.name,
        error="source_name_not_stamped",
    )
    raw = _read_bounded_regular(source, max_bytes=_MAX_SOURCE_BYTES)
    generated_at = _validate_payload(
        raw,
        slippage_artifact_path=(
            Path(slippage_artifact_path)
            if slippage_artifact_path is not None
            else None
        ),
    )
    evaluated_at = _normalize_now(now_utc)
    if source_stamp > generated_at:
        raise CandidateBoardPublishError("filename_stamp_after_generated_at")
    future_boundary = evaluated_at + timedelta(seconds=_MAX_FUTURE_SKEW_SECONDS)
    if source_stamp > future_boundary:
        raise CandidateBoardPublishError("filename_stamp_from_future")
    if generated_at > future_boundary:
        raise CandidateBoardPublishError("payload_generated_at_from_future")
    if isinstance(retention_limit, bool) or not isinstance(retention_limit, int):
        raise CandidateBoardPublishError("retention_limit_invalid")
    if not 1 <= retention_limit <= 128:
        raise CandidateBoardPublishError("retention_limit_invalid")
    if (
        isinstance(max_total_bytes, bool)
        or not isinstance(max_total_bytes, int)
        or not 1 <= max_total_bytes <= _CONSUMER_MAX_TOTAL_BYTES
        or len(raw) > max_total_bytes
    ):
        raise CandidateBoardPublishError("max_total_bytes_invalid")

    destination = Path(destination_directory)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination_stat = destination.lstat()
    if (
        not stat.S_ISDIR(destination_stat.st_mode)
        or stat.S_ISLNK(destination_stat.st_mode)
    ):
        raise CandidateBoardPublishError("destination_not_private_directory")
    if destination_stat.st_mode & 0o077:
        raise CandidateBoardPublishError("destination_not_private_directory")

    lock_descriptor = _acquire_destination_lock(destination)
    try:
        return _publish_locked(
            source=source,
            destination=destination,
            raw=raw,
            source_stamp=source_stamp,
            retention_limit=retention_limit,
            max_total_bytes=max_total_bytes,
        )
    finally:
        _release_destination_lock(lock_descriptor)


def _publish_locked(
    *,
    source: Path,
    destination: Path,
    raw: bytes,
    source_stamp: datetime,
    retention_limit: int,
    max_total_bytes: int,
) -> dict[str, Any]:
    """持有 destination flock 後完成 enumerate 到 durable prune 的完整交易。"""
    published = destination / source.name
    retained = _stamped_files(destination)
    if published in retained:
        if _read_bounded_regular(published, max_bytes=_MAX_SOURCE_BYTES) != raw:
            raise CandidateBoardPublishError("immutable_destination_collision")
        if published != retained[-1]:
            return _publish_result(
                status="ALREADY_PUBLISHED_STALE",
                published=published,
                raw=raw,
                retention_limit=retention_limit,
                retained_file_count=len(retained),
                retained_total_bytes=_total_bytes(retained),
            )
        original_count = len(retained)
        original_total_bytes = _total_bytes(retained)
        retained = _prune_to_bounds(
            retained,
            protected=published,
            incoming_bytes=0,
            retention_limit=retention_limit,
            max_total_bytes=max_total_bytes,
        )
        if (
            len(retained) != original_count
            or _total_bytes(retained) != original_total_bytes
        ):
            directory_fd = os.open(
                destination,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        return _publish_result(
            status="ALREADY_PUBLISHED",
            published=published,
            raw=raw,
            retention_limit=retention_limit,
            retained_file_count=len(retained),
            retained_total_bytes=_total_bytes(retained),
        )
    if retained and source_stamp <= _filename_stamp(
        retained[-1].name,
        error="unsafe_destination_file",
    ):
        raise CandidateBoardPublishError("source_stamp_not_newer_than_destination")
    temp_path: Path | None = None
    directory_fd: int | None = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=".alr-candidate-board-", dir=destination)
        temp_path = Path(temp_name)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(
            destination,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        # hard-link 是 no-replace 的原子 visibility boundary；同名檔不會被覆寫。
        os.link(temp_path, published)
        try:
            # 先保證新 link durable，才可刪除任何 last-known-good snapshot。
            os.fsync(directory_fd)
        except OSError:
            published.unlink(missing_ok=True)
            temp_path.unlink(missing_ok=True)
            temp_path = None
            try:
                os.fsync(directory_fd)
            except OSError:
                pass
            raise
        temp_path.unlink()
        temp_path = None
        _prune_to_bounds(
            _stamped_files(destination),
            protected=published,
            incoming_bytes=0,
            retention_limit=retention_limit,
            max_total_bytes=max_total_bytes,
        )
        os.fsync(directory_fd)
    except FileExistsError as exc:
        raise CandidateBoardPublishError("immutable_destination_collision") from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return _publish_result(
        status="PUBLISHED",
        published=published,
        raw=raw,
        retention_limit=retention_limit,
        retained_file_count=len(_stamped_files(destination)),
        retained_total_bytes=_total_bytes(_stamped_files(destination)),
    )


def _acquire_destination_lock(destination: Path) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    cloexec = getattr(os, "O_CLOEXEC", None)
    if nofollow is None or cloexec is None:
        raise CandidateBoardPublishError("destination_lock_secure_open_unavailable")
    lock_path = destination / _LOCK_FILE_NAME
    try:
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | nofollow | cloexec,
            0o600,
        )
    except OSError as exc:
        raise CandidateBoardPublishError("destination_lock_invalid") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise CandidateBoardPublishError("destination_lock_invalid")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise CandidateBoardPublishError(
                    "destination_lock_unavailable"
                ) from exc
            raise CandidateBoardPublishError("destination_lock_invalid") from exc
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _release_destination_lock(descriptor: int) -> None:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _publish_result(
    *,
    status: str,
    published: Path,
    raw: bytes,
    retention_limit: int,
    retained_file_count: int,
    retained_total_bytes: int,
) -> dict[str, Any]:
    return {
        "schema_version": "alr_candidate_board_publish_result_v2",
        "status": status,
        "published_path": str(published),
        "source_content_sha256": hashlib.sha256(raw).hexdigest(),
        "retention_limit": retention_limit,
        "retained_file_count": retained_file_count,
        "retained_total_bytes": retained_total_bytes,
        "latest_alias_written": False,
    }


def _validate_payload(
    raw: bytes,
    *,
    slippage_artifact_path: Path | None,
) -> datetime:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non_finite:{value}")

    try:
        payload = json.loads(raw, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CandidateBoardPublishError("source_json_invalid") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != SOURCE_SCHEMA_VERSION
    ):
        raise CandidateBoardPublishError("source_schema_invalid")
    generated_at = payload.get("generated_at_utc")
    if not isinstance(generated_at, str):
        raise CandidateBoardPublishError("generated_at_invalid")
    try:
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateBoardPublishError("generated_at_invalid") from exc
    if (
        generated.tzinfo is None
        or generated.utcoffset() != timezone.utc.utcoffset(generated)
    ):
        raise CandidateBoardPublishError("generated_at_invalid")
    board = payload.get("learning_candidate_board")
    if not isinstance(board, dict) or board.get("schema_version") != BOARD_SCHEMA_VERSION:
        raise CandidateBoardPublishError("board_schema_invalid")
    if board.get("candidate_universe_complete") is not True:
        raise CandidateBoardPublishError("candidate_universe_incomplete")
    try:
        validate_learning_candidate_board_v2(board)
    except ValueError as exc:
        raise CandidateBoardPublishError(str(exc)) from exc
    if board.get("as_of_utc_date") != generated.date().isoformat():
        raise CandidateBoardPublishError("board_as_of_generated_at_mismatch")
    basis = payload.get("cost_basis_main")
    if basis not in {"conservative_v1", "expected_slippage_mean_abs_v1"}:
        raise CandidateBoardPublishError("cost_basis_main_invalid")
    projected = None
    if basis == "expected_slippage_mean_abs_v1":
        projected = _validate_independent_expected_cost_artifact(
            payload,
            generated_at=generated.astimezone(timezone.utc),
            slippage_artifact_path=slippage_artifact_path,
        )
    _validate_outer_and_board_cost_contract(
        payload,
        board=board,
        projected=projected,
    )
    return generated.astimezone(timezone.utc)


def _validate_independent_expected_cost_artifact(
    payload: Mapping[str, Any],
    *,
    generated_at: datetime,
    slippage_artifact_path: Path | None,
) -> dict[str, Any]:
    if slippage_artifact_path is None:
        raise CandidateBoardPublishError(
            "expected_cost_independent_artifact_required"
        )
    try:
        raw = _read_bounded_regular(
            slippage_artifact_path,
            max_bytes=_MAX_SLIPPAGE_ARTIFACT_BYTES,
        )
    except (CandidateBoardPublishError, OSError) as exc:
        raise CandidateBoardPublishError(
            "expected_cost_independent_artifact_invalid"
        ) from exc

    def reject_constant(value: str) -> None:
        raise ValueError(f"non_finite:{value}")

    try:
        independent_payload = json.loads(raw, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CandidateBoardPublishError(
            "expected_cost_independent_artifact_invalid"
        ) from exc
    projected = _load_expected_slippage(
        independent_payload,
        now=generated_at,
    )
    if projected is None:
        raise CandidateBoardPublishError(
            "expected_cost_independent_artifact_invalid"
        )
    expected = {
        "available": True,
        "asof": projected["asof"],
        "source_asof_utc": projected["asof"],
        "source_payload_sha256": projected["source_payload_sha256"],
        "source_payload": projected["source_payload"],
        "normalized_projection": projected["normalized_projection"],
        "normalized_projection_sha256": projected[
            "normalized_projection_sha256"
        ],
        "global_mean_abs_bps": projected["global_mean_abs"],
        "global_tail_bps": projected["global_tail_bps"],
        "global_tail_metric": projected["global_tail_metric"],
        "n_total_global": projected["n_total_global"],
        "max_age_hours": QUANTILE_ARTIFACT_MAX_AGE_HOURS,
    }
    if not _exact_value_equal(payload.get("expected_cost_artifact"), expected):
        raise CandidateBoardPublishError(
            "expected_cost_independent_artifact_mismatch"
        )
    return projected


def _validate_outer_and_board_cost_contract(
    payload: Mapping[str, Any],
    *,
    board: Mapping[str, Any],
    projected: Mapping[str, Any] | None,
) -> None:
    if projected is None:
        expected_outer = {
            "available": False,
            "asof": None,
            "source_asof_utc": None,
            "source_payload_sha256": None,
            "source_payload": None,
            "normalized_projection": None,
            "normalized_projection_sha256": None,
            "global_mean_abs_bps": None,
            "global_tail_bps": None,
            "global_tail_metric": None,
            "n_total_global": 0,
            "max_age_hours": QUANTILE_ARTIFACT_MAX_AGE_HOURS,
        }
    else:
        expected_outer = {
            "available": True,
            "asof": projected["asof"],
            "source_asof_utc": projected["asof"],
            "source_payload_sha256": projected["source_payload_sha256"],
            "source_payload": projected["source_payload"],
            "normalized_projection": projected["normalized_projection"],
            "normalized_projection_sha256": projected[
                "normalized_projection_sha256"
            ],
            "global_mean_abs_bps": projected["global_mean_abs"],
            "global_tail_bps": projected["global_tail_bps"],
            "global_tail_metric": projected["global_tail_metric"],
            "n_total_global": projected["n_total_global"],
            "max_age_hours": QUANTILE_ARTIFACT_MAX_AGE_HOURS,
        }
    if not _exact_value_equal(payload.get("expected_cost_artifact"), expected_outer):
        raise CandidateBoardPublishError("outer_cost_evidence_mismatch")
    outer_expected_basis = (
        "expected_slippage_mean_abs_v1"
        if projected is not None
        else "conservative_v1"
    )
    if payload.get("cost_basis_main") != outer_expected_basis:
        raise CandidateBoardPublishError("outer_cost_evidence_mismatch")
    rows = board.get("candidate_rows")
    if not isinstance(rows, list):
        raise CandidateBoardPublishError("candidate_rows_invalid")
    for row in rows:
        try:
            symbol = row["arbiter_input"]["identity"]["symbol"]
            target_date_raw = row["arbiter_input"]["identity"][
                "target_regime"
            ]["utc_date"]
            if not isinstance(target_date_raw, str):
                raise ValueError
            target_date = datetime.fromisoformat(target_date_raw).date()
            if target_date.isoformat() != target_date_raw:
                raise ValueError
            actual = row["arbiter_input"]["cost_evidence"]
        except (KeyError, TypeError, ValueError):
            raise CandidateBoardPublishError("candidate_cost_evidence_mismatch") from None
        row_projected = candidate_cost_projection_for_recorded_date(
            projected,
            as_of_date=target_date + timedelta(days=1),
        )
        expected = candidate_cost_evidence_v2(row_projected, symbol=symbol)
        row_expected_basis = (
            "expected_slippage_mean_abs_v1"
            if row_projected is not None
            else "conservative_v1"
        )
        if (
            row.get("cost_basis_main") != row_expected_basis
            or not _exact_value_equal(actual, expected)
        ):
            raise CandidateBoardPublishError("candidate_cost_evidence_mismatch")


def _exact_value_equal(left: Any, right: Any) -> bool:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(
            _exact_value_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _exact_value_equal(a, b) for a, b in zip(left, right)
        )
    if type(left) is not type(right):
        return False
    if type(left) is float and left == right == 0.0:
        return math.copysign(1.0, left) == math.copysign(1.0, right)
    return left == right


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stamped_files(destination: Path) -> list[Path]:
    stamped: list[Path] = []
    for path in destination.iterdir():
        if path.name.startswith("blocked_outcome_review_"):
            if _STAMPED_NAME_RE.fullmatch(path.name) is None:
                raise CandidateBoardPublishError("unsafe_destination_file")
            _filename_stamp(path.name, error="unsafe_destination_file")
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise CandidateBoardPublishError("unsafe_destination_file")
            stamped.append(path)
    return sorted(stamped)


def _filename_stamp(name: str, *, error: str) -> datetime:
    match = _STAMPED_NAME_RE.fullmatch(name)
    if match is None:
        raise CandidateBoardPublishError(error)
    try:
        parsed = datetime.strptime(match.group("stamp"), "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise CandidateBoardPublishError(error) from exc
    return parsed.replace(tzinfo=timezone.utc)


def _normalize_now(value: datetime | None) -> datetime:
    candidate = datetime.now(timezone.utc) if value is None else value
    if not isinstance(candidate, datetime) or candidate.tzinfo is None:
        raise CandidateBoardPublishError("now_utc_invalid")
    offset = candidate.utcoffset()
    if offset is None:
        raise CandidateBoardPublishError("now_utc_invalid")
    return candidate.astimezone(timezone.utc)


def _prune_to_bounds(
    retained: list[Path],
    *,
    protected: Path | None,
    incoming_bytes: int,
    retention_limit: int,
    max_total_bytes: int,
) -> list[Path]:
    remaining = list(retained)
    while (
        len(remaining) > retention_limit
        or _total_bytes(remaining) + incoming_bytes > max_total_bytes
    ):
        removable = next((path for path in remaining if path != protected), None)
        if removable is None:
            raise CandidateBoardPublishError("retention_bounds_unsatisfiable")
        removable.unlink()
        remaining.remove(removable)
    return remaining


def _total_bytes(paths: list[Path]) -> int:
    return sum(path.stat().st_size for path in paths)


def _read_bounded_regular(path: Path, *, max_bytes: int) -> bytes:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    cloexec = getattr(os, "O_CLOEXEC", None)
    if nofollow is None or cloexec is None:
        raise CandidateBoardPublishError("secure_open_unavailable")
    try:
        descriptor = os.open(path, os.O_RDONLY | nofollow | cloexec)
    except OSError as exc:
        reason = (
            "source_not_regular"
            if exc.errno in {errno.ELOOP, errno.EISDIR}
            else "source_unavailable"
        )
        raise CandidateBoardPublishError(reason) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise CandidateBoardPublishError("source_not_regular")
        if not 0 < before.st_size <= max_bytes:
            raise CandidateBoardPublishError("source_size_invalid")
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after or len(raw) != before.st_size:
            raise CandidateBoardPublishError("source_changed_during_read")
        return raw
    finally:
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    """CLI 僅發布已完成的 stamped board，任何 contract 缺口皆非零退出。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--slippage-artifact", type=Path)
    parser.add_argument("--retention-limit", required=True, type=int)
    parser.add_argument(
        "--max-total-bytes",
        type=int,
        default=_CONSUMER_MAX_TOTAL_BYTES,
    )
    arguments = parser.parse_args(argv)
    slippage_artifact = (
        arguments.slippage_artifact
        if arguments.slippage_artifact is not None
        else arguments.source.parent / "slippage_quantiles_latest.json"
    )
    try:
        result = publish_candidate_board(
            arguments.source,
            arguments.destination,
            retention_limit=arguments.retention_limit,
            slippage_artifact_path=slippage_artifact,
            max_total_bytes=arguments.max_total_bytes,
        )
    except (CandidateBoardPublishError, OSError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "alr_candidate_board_publish_result_v2",
                    "status": "PUBLISH_FAILED",
                    "reason": str(exc),
                    "latest_alias_written": False,
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
