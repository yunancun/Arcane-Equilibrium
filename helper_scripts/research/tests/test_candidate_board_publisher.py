"""ALR candidate board 專用 rendezvous publisher 行為測試。"""

from __future__ import annotations

import hashlib
import json
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cost_gate_learning_lane import candidate_board_publisher as publisher
from cost_gate_learning_lane.candidate_board_publisher import (
    CandidateBoardPublishError,
    publish_candidate_board,
)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_review(
    path: Path,
    *,
    generated_at_utc: str = "2026-07-10T12:00:00Z",
) -> bytes:
    board = {
        "schema_version": "cost_gate_learning_candidate_board_v1",
        "candidate_universe_complete": True,
        "candidate_rows": [],
    }
    board["board_hash"] = _canonical_hash(board)
    payload = {
        "schema_version": "cost_gate_demo_learning_lane_blocked_outcome_review_v5",
        "generated_at_utc": generated_at_utc,
        "learning_candidate_board": board,
    }
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def _rewrite_review(path: Path, mutate: object) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    board = payload.get("learning_candidate_board")
    if isinstance(board, dict):
        board["board_hash"] = _canonical_hash(
            {key: value for key, value in board.items() if key != "board_hash"}
        )
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def test_publishes_byte_identical_private_stamped_snapshot_only(tmp_path: Path) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    expected = _write_review(source)
    destination = tmp_path / "rendezvous"

    result = publish_candidate_board(
        source,
        destination,
        retention_limit=128,
    )

    published = destination / source.name
    assert result["status"] == "PUBLISHED"
    assert result["published_path"] == str(published)
    assert published.read_bytes() == expected
    assert published.stat().st_mode & 0o777 == 0o600
    assert sorted(path.name for path in destination.iterdir() if not path.name.startswith(".")) == [
        source.name
    ]
    assert not (destination / "blocked_outcome_review_latest.json").exists()


def test_retention_prunes_oldest_before_publish_and_never_exceeds_limit(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    for stamp in ("20260710T090000Z", "20260710T100000Z", "20260710T110000Z"):
        _write_review(destination / f"blocked_outcome_review_{stamp}.json")
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)

    result = publish_candidate_board(source, destination, retention_limit=3)

    names = sorted(path.name for path in destination.glob("blocked_outcome_review_*.json"))
    assert result["retained_file_count"] == 3
    assert names == [
        "blocked_outcome_review_20260710T100000Z.json",
        "blocked_outcome_review_20260710T110000Z.json",
        "blocked_outcome_review_20260710T120000Z.json",
    ]


@pytest.mark.parametrize(
    "unsafe_name",
    (
        "blocked_outcome_review_latest.json",
        "blocked_outcome_review_partial.json",
    ),
)
def test_refuses_consumer_poisoning_alias_or_partial_file(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    (destination / unsafe_name).write_text("{}\n", encoding="utf-8")
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)

    with pytest.raises(CandidateBoardPublishError, match="unsafe_destination_file"):
        publish_candidate_board(source, destination, retention_limit=128)

    assert not (destination / source.name).exists()


def test_identical_retry_is_idempotent_without_rewriting_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    destination = tmp_path / "rendezvous"
    first = publish_candidate_board(source, destination, retention_limit=128)
    first_inode = (destination / source.name).stat().st_ino

    second = publish_candidate_board(source, destination, retention_limit=128)

    assert first["status"] == "PUBLISHED"
    assert second["status"] == "ALREADY_PUBLISHED"
    assert (destination / source.name).stat().st_ino == first_inode


def test_source_is_bounded_read_from_one_no_follow_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    observed_flags: list[int] = []
    original_open = publisher.os.open

    def recording_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if Path(path) == source:
            observed_flags.append(flags)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(publisher.os, "open", recording_open)

    publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)

    assert len(observed_flags) == 1
    assert observed_flags[0] & publisher.os.O_NOFOLLOW
    assert observed_flags[0] & publisher.os.O_CLOEXEC


def test_retention_also_prunes_to_consumer_total_byte_bound(tmp_path: Path) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    existing: list[Path] = []
    for stamp in ("20260710T090000Z", "20260710T100000Z", "20260710T110000Z"):
        path = destination / f"blocked_outcome_review_{stamp}.json"
        _write_review(path)
        existing.append(path)
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    raw = _write_review(source)
    byte_bound = len(raw) * 2

    result = publish_candidate_board(
        source,
        destination,
        retention_limit=128,
        max_total_bytes=byte_bound,
    )

    retained = sorted(destination.glob("blocked_outcome_review_*.json"))
    assert [path.name for path in retained] == [
        "blocked_outcome_review_20260710T110000Z.json",
        "blocked_outcome_review_20260710T120000Z.json",
    ]
    assert result["retained_total_bytes"] <= byte_bound


@pytest.mark.parametrize(
    ("mutate", "reason"),
    (
        (lambda payload: payload.pop("generated_at_utc"), "generated_at_invalid"),
        (
            lambda payload: payload["learning_candidate_board"].__setitem__(
                "candidate_rows", {}
            ),
            "candidate_rows_invalid",
        ),
        (
            lambda payload: payload["learning_candidate_board"].__setitem__(
                "candidate_rows", ["not-a-mapping"]
            ),
            "candidate_rows_invalid",
        ),
    ),
)
def test_publisher_rejects_source_shapes_the_consumer_cannot_load(
    tmp_path: Path,
    mutate: object,
    reason: str,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    _rewrite_review(source, mutate)

    with pytest.raises(CandidateBoardPublishError, match=reason):
        publish_candidate_board(source, tmp_path / "rendezvous", retention_limit=128)


def test_failed_atomic_link_does_not_prune_last_good_snapshots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    original_names = [
        "blocked_outcome_review_20260710T100000Z.json",
        "blocked_outcome_review_20260710T110000Z.json",
    ]
    for name in original_names:
        _write_review(destination / name)
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    monkeypatch.setattr(
        publisher.os,
        "link",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("simulated link failure")),
    )

    with pytest.raises(OSError, match="simulated link failure"):
        publish_candidate_board(source, destination, retention_limit=2)

    assert sorted(path.name for path in destination.glob("blocked_outcome_review_*.json")) == original_names


def test_failed_first_directory_fsync_rolls_back_new_link_before_pruning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    original_names = [
        "blocked_outcome_review_20260710T100000Z.json",
        "blocked_outcome_review_20260710T110000Z.json",
    ]
    for name in original_names:
        _write_review(destination / name)
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source)
    original_fsync = publisher.os.fsync
    directory_fsync_calls = 0

    def fail_first_directory_fsync(descriptor: int) -> None:
        nonlocal directory_fsync_calls
        if stat.S_ISDIR(publisher.os.fstat(descriptor).st_mode):
            directory_fsync_calls += 1
            if directory_fsync_calls == 1:
                raise OSError("simulated directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(publisher.os, "fsync", fail_first_directory_fsync)

    with pytest.raises(OSError, match="simulated directory fsync failure"):
        publish_candidate_board(source, destination, retention_limit=2)

    assert sorted(path.name for path in destination.glob("blocked_outcome_review_*.json")) == original_names


def test_identical_retry_applies_lowered_retention_without_rewrite(tmp_path: Path) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    names = [
        "blocked_outcome_review_20260710T100000Z.json",
        "blocked_outcome_review_20260710T110000Z.json",
        "blocked_outcome_review_20260710T120000Z.json",
    ]
    for name in names:
        _write_review(destination / name)
    source = tmp_path / names[-1]
    _write_review(source)
    inode = (destination / source.name).stat().st_ino

    result = publish_candidate_board(source, destination, retention_limit=2)

    assert result["status"] == "ALREADY_PUBLISHED"
    assert result["retained_file_count"] == 2
    assert (destination / source.name).stat().st_ino == inode
    assert sorted(path.name for path in destination.glob("blocked_outcome_review_*.json")) == names[-2:]


def test_stale_new_snapshot_cannot_replace_newer_retained_evidence(tmp_path: Path) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    newest_names = [
        "blocked_outcome_review_20260710T110000Z.json",
        "blocked_outcome_review_20260710T120000Z.json",
    ]
    for name in newest_names:
        _write_review(destination / name)
    source = tmp_path / "blocked_outcome_review_20260710T090000Z.json"
    _write_review(source)

    with pytest.raises(
        CandidateBoardPublishError,
        match="source_stamp_not_newer_than_destination",
    ):
        publish_candidate_board(source, destination, retention_limit=1)

    assert sorted(path.name for path in destination.glob("blocked_outcome_review_*.json")) == newest_names


def test_stale_identical_retry_never_prunes_newer_evidence(tmp_path: Path) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    names = [
        "blocked_outcome_review_20260710T090000Z.json",
        "blocked_outcome_review_20260710T110000Z.json",
        "blocked_outcome_review_20260710T120000Z.json",
    ]
    for name in names:
        _write_review(destination / name)
    source = tmp_path / names[0]
    _write_review(source)

    result = publish_candidate_board(source, destination, retention_limit=1)

    assert result["status"] == "ALREADY_PUBLISHED_STALE"
    assert sorted(path.name for path in destination.glob("blocked_outcome_review_*.json")) == names


def test_filename_stamp_cannot_be_after_payload_generation_time(tmp_path: Path) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120001Z.json"
    _write_review(source, generated_at_utc="2026-07-10T12:00:00Z")

    with pytest.raises(
        CandidateBoardPublishError,
        match="filename_stamp_after_generated_at",
    ):
        publish_candidate_board(
            source,
            tmp_path / "rendezvous",
            retention_limit=128,
            now_utc=datetime(2026, 7, 10, 13, tzinfo=timezone.utc),
        )


def test_filename_stamp_future_poison_exceeding_skew_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120006Z.json"
    _write_review(source, generated_at_utc="2026-07-10T12:00:06Z")

    with pytest.raises(CandidateBoardPublishError, match="filename_stamp_from_future"):
        publish_candidate_board(
            source,
            tmp_path / "rendezvous",
            retention_limit=128,
            now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        )


def test_payload_generation_future_poison_exceeding_skew_is_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    _write_review(source, generated_at_utc="2026-07-10T12:00:06Z")

    with pytest.raises(CandidateBoardPublishError, match="payload_generated_at_from_future"):
        publish_candidate_board(
            source,
            tmp_path / "rendezvous",
            retention_limit=128,
            now_utc=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
        )


def test_interleaved_newer_publish_cannot_enter_after_older_precheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "rendezvous"
    destination.mkdir(mode=0o700)
    _write_review(destination / "blocked_outcome_review_20260710T110000Z.json")
    older = tmp_path / "blocked_outcome_review_20260710T120000Z.json"
    newer = tmp_path / "blocked_outcome_review_20260710T130000Z.json"
    _write_review(older, generated_at_utc="2026-07-10T12:00:00Z")
    _write_review(newer, generated_at_utc="2026-07-10T13:00:00Z")
    older_enumerated = threading.Event()
    release_older = threading.Event()
    original_stamped_files = publisher._stamped_files
    older_first_enumeration = True

    def pause_older_after_precheck(path: Path) -> list[Path]:
        nonlocal older_first_enumeration
        retained = original_stamped_files(path)
        if threading.current_thread().name == "older-publisher" and older_first_enumeration:
            older_first_enumeration = False
            older_enumerated.set()
            assert release_older.wait(timeout=5)
        return retained

    monkeypatch.setattr(publisher, "_stamped_files", pause_older_after_precheck)
    older_result: list[dict[str, object]] = []
    older_errors: list[BaseException] = []

    def publish_older() -> None:
        try:
            older_result.append(
                publish_candidate_board(
                    older,
                    destination,
                    retention_limit=1,
                    now_utc=datetime(2026, 7, 10, 14, tzinfo=timezone.utc),
                )
            )
        except BaseException as exc:  # noqa: BLE001 - thread must report to test.
            older_errors.append(exc)

    thread = threading.Thread(target=publish_older, name="older-publisher")
    thread.start()
    assert older_enumerated.wait(timeout=5)
    try:
        with pytest.raises(
            CandidateBoardPublishError,
            match="destination_lock_unavailable",
        ):
            publish_candidate_board(
                newer,
                destination,
                retention_limit=1,
                now_utc=datetime(2026, 7, 10, 14, tzinfo=timezone.utc),
            )
    finally:
        release_older.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert older_errors == []
    assert older_result[0]["status"] == "PUBLISHED"
    assert [path.name for path in destination.glob("blocked_outcome_review_*.json")] == [
        older.name
    ]
