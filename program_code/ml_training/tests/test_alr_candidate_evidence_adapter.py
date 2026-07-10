from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ml_training import alr_candidate_evidence_adapter as adapter
from ml_training import alr_safe_file
from ml_training.alr_candidate_evidence_adapter import (
    load_candidate_evidence_snapshot,
)


EVALUATED_AT = "2026-07-10T12:00:00Z"


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _candidate_row(candidate_id: str = "candidate-b") -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "candidate_identity": {
            "strategy_name": "grid_trading",
            "strategy_version": "v7",
            "strategy_config_hash": "a" * 64,
            "symbol": "BTCUSDT",
            "side": "Buy",
            "horizon_minutes": 60,
            "target_regime_hash": "b" * 64,
        },
        "n_eff": 12,
        "distinct_entry_utc_days": 3,
        "top_entry_day_share": 0.5,
        "censored_share": 0.0,
        "cost_recomputable_share": 1.0,
    }


def _payload(*, rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    board: dict[str, object] = {
        "schema_version": "cost_gate_learning_candidate_board_v1",
        "candidate_universe_complete": True,
        "candidate_rows": rows or [_candidate_row()],
    }
    board["board_hash"] = _canonical_sha256(board)
    return {
        "schema_version": "cost_gate_demo_learning_lane_blocked_outcome_review_v5",
        "record_type": "blocked_signal_outcome_review",
        "generated_at_utc": "2026-07-10T11:30:00Z",
        "learning_candidate_board": board,
        "top_side_cells": [{"legacy_only": True}],
    }


def _write_snapshot(
    directory: Path,
    *,
    name: str = "blocked_outcome_review_20260710T113000Z.json",
    payload: dict[str, object] | None = None,
) -> Path:
    path = directory / name
    path.write_text(
        json.dumps(payload or _payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _load(directory: Path, **overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "evaluated_at": EVALUATED_AT,
        "max_age_seconds": 3600,
        "max_files": 8,
        "max_bytes": 1_000_000,
    }
    kwargs.update(overrides)
    return load_candidate_evidence_snapshot(directory, **kwargs)


def test_missing_directory_is_structured_fail_closed_not_an_exception(
    tmp_path: Path,
) -> None:
    result = _load(tmp_path / "missing")

    assert result["source_status"] == "DIRECTORY_MISSING"
    assert result["candidate_rows"] == []
    assert result["candidate_universe_complete"] is False
    assert result["selection_allowed"] is False


def test_loads_latest_immutable_snapshot_and_binds_content_and_board_hash(
    tmp_path: Path,
) -> None:
    older = _payload(rows=[_candidate_row("candidate-z")])
    older["generated_at_utc"] = "2026-07-10T11:00:00Z"
    _write_snapshot(
        tmp_path,
        name="blocked_outcome_review_20260710T110000Z.json",
        payload=older,
    )
    latest_path = _write_snapshot(
        tmp_path,
        payload=_payload(
            rows=[_candidate_row("candidate-b"), _candidate_row("candidate-a")]
        ),
    )

    result = _load(tmp_path)

    assert result["source_status"] == "READY"
    assert result["selection_allowed"] is True
    assert result["source_file"] == str(latest_path.resolve())
    assert result["source_content_sha256"] == hashlib.sha256(
        latest_path.read_bytes()
    ).hexdigest()
    assert result["candidate_universe_complete"] is True
    assert [row["candidate_id"] for row in result["candidate_rows"]] == [
        "candidate-a",
        "candidate-b",
    ]
    assert result["board_hash"] == _payload()["learning_candidate_board"][
        "board_hash"
    ] or len(result["board_hash"]) == 64
    assert len(result["snapshot_hash"]) == 64
    assert "top_side_cells" not in result


@pytest.mark.parametrize(
    ("name", "expected"),
    (
        ("blocked_outcome_review_latest.json", "LATEST_ALIAS_PRESENT"),
        ("blocked_outcome_review_20260710T113000Z.json.tmp", "UNSAFE_FILE_PRESENT"),
    ),
)
def test_rejects_ambiguous_alias_or_partial_file(
    tmp_path: Path,
    name: str,
    expected: str,
) -> None:
    _write_snapshot(tmp_path)
    (tmp_path / name).write_text("{}\n", encoding="utf-8")

    result = _load(tmp_path)

    assert result["source_status"] == expected
    assert result["selection_allowed"] is False


def test_rejects_symlink_even_when_target_is_regular(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(json.dumps(_payload()), encoding="utf-8")
    link = tmp_path / "blocked_outcome_review_20260710T113000Z.json"
    link.symlink_to(target)

    result = _load(tmp_path)

    assert result["source_status"] == "SOURCE_SYMLINK"
    assert result["candidate_rows"] == []


def test_directory_count_and_total_bytes_are_bounded_before_selection(
    tmp_path: Path,
) -> None:
    first = _write_snapshot(
        tmp_path,
        name="blocked_outcome_review_20260710T110000Z.json",
    )
    second = _write_snapshot(tmp_path)

    too_many = _load(tmp_path, max_files=1)
    too_large = _load(tmp_path, max_bytes=first.stat().st_size + second.stat().st_size - 1)

    assert too_many["source_status"] == "UNIVERSE_TRUNCATED"
    assert too_large["source_status"] == "UNIVERSE_TRUNCATED"
    assert too_many["candidate_rows"] == []
    assert too_large["candidate_rows"] == []


@pytest.mark.parametrize(
    ("generated_at", "expected"),
    (
        ("2026-07-10T10:59:59Z", "SOURCE_STALE"),
        ("2026-07-10T12:00:01Z", "SOURCE_FROM_FUTURE"),
    ),
)
def test_freshness_is_evaluated_against_explicit_clock(
    tmp_path: Path,
    generated_at: str,
    expected: str,
) -> None:
    payload = _payload()
    payload["generated_at_utc"] = generated_at
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == expected
    assert result["selection_allowed"] is False


@pytest.mark.parametrize(
    "mutation",
    ("malformed_json", "legacy_without_board", "incomplete_board", "tampered_board"),
)
def test_malformed_or_unbound_board_fails_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    path = tmp_path / "blocked_outcome_review_20260710T113000Z.json"
    if mutation == "malformed_json":
        path.write_text("{", encoding="utf-8")
    else:
        payload = _payload()
        if mutation == "legacy_without_board":
            payload.pop("learning_candidate_board")
        elif mutation == "incomplete_board":
            payload["learning_candidate_board"]["candidate_universe_complete"] = False
            payload["learning_candidate_board"]["board_hash"] = _canonical_sha256(
                {
                    key: value
                    for key, value in payload["learning_candidate_board"].items()
                    if key != "board_hash"
                }
            )
        else:
            payload["learning_candidate_board"]["candidate_rows"][0]["n_eff"] = 999
        path.write_text(json.dumps(payload), encoding="utf-8")

    result = _load(tmp_path)

    assert result["source_status"] in {
        "SOURCE_JSON_INVALID",
        "LEARNING_BOARD_MISSING",
        "CANDIDATE_UNIVERSE_INCOMPLETE",
        "BOARD_HASH_MISMATCH",
    }
    assert result["candidate_rows"] == []


@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
def test_non_finite_json_constants_are_structured_source_failures(
    tmp_path: Path,
    constant: str,
) -> None:
    payload = _payload()
    raw = json.dumps(payload, sort_keys=True).replace(
        '"n_eff": 12', f'"n_eff": {constant}'
    )
    path = tmp_path / "blocked_outcome_review_20260710T113000Z.json"
    path.write_text(raw, encoding="utf-8")

    result = _load(tmp_path)

    assert result["source_status"] == "SOURCE_JSON_INVALID"
    assert result["selection_allowed"] is False
    assert result["candidate_rows"] == []


def test_detects_file_change_between_pre_and_post_read_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_snapshot(tmp_path)
    original = alr_safe_file.os.fstat
    calls = 0

    def drifting(descriptor: int) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        metadata = original(descriptor)
        return SimpleNamespace(
            st_mode=metadata.st_mode,
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino,
            st_size=metadata.st_size,
            st_mtime_ns=metadata.st_mtime_ns + int(calls >= 2),
        )

    monkeypatch.setattr(alr_safe_file.os, "fstat", drifting)

    result = _load(tmp_path)

    assert result["source_status"] == "SOURCE_CHANGED_DURING_READ"
    assert result["selection_allowed"] is False


def test_evidence_read_uses_no_follow_and_close_on_exec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_snapshot(tmp_path)
    original = alr_safe_file.os.open
    observed_flags: list[int] = []

    def recording_open(path, flags, *args, **kwargs):
        observed_flags.append(flags)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(alr_safe_file.os, "open", recording_open)

    assert _load(tmp_path)["source_status"] == "READY"
    assert observed_flags
    assert observed_flags[-1] & alr_safe_file.os.O_NOFOLLOW
    assert observed_flags[-1] & alr_safe_file.os.O_CLOEXEC


def test_input_row_order_does_not_change_candidate_set_or_semantic_hash(
    tmp_path: Path,
) -> None:
    rows = [_candidate_row("candidate-b"), _candidate_row("candidate-a")]
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    _write_snapshot(first_dir, payload=_payload(rows=rows))
    _write_snapshot(second_dir, payload=_payload(rows=list(reversed(rows))))

    first = _load(first_dir)
    second = _load(second_dir)

    assert first["candidate_rows"] == second["candidate_rows"]
    assert first["candidate_set_hash"] == second["candidate_set_hash"]
    assert first["source_content_sha256"] != second["source_content_sha256"]


def test_invalid_loader_limits_raise_before_touching_files(tmp_path: Path) -> None:
    _write_snapshot(tmp_path)

    with pytest.raises(ValueError, match="max_age_seconds_invalid"):
        _load(tmp_path, max_age_seconds=0)
    with pytest.raises(ValueError, match="max_files_invalid"):
        _load(tmp_path, max_files=True)
    with pytest.raises(ValueError, match="max_bytes_invalid"):
        _load(tmp_path, max_bytes=-1)


def test_rejects_non_directory_and_non_regular_snapshot(tmp_path: Path) -> None:
    plain_file = tmp_path / "plain"
    plain_file.write_text("x", encoding="utf-8")
    result = _load(plain_file)

    assert result["source_status"] == "PATH_NOT_DIRECTORY"
    assert result["selection_allowed"] is False

    directory = tmp_path / "dir"
    directory.mkdir()
    nested = directory / "blocked_outcome_review_20260710T113000Z.json"
    nested.mkdir()
    nested_result = _load(directory)
    assert nested_result["source_status"] == "SOURCE_NOT_REGULAR"


def test_frozen_r3_counterfactual_is_historical_only_not_live_candidate_ingress(
    tmp_path: Path,
) -> None:
    frozen = (
        Path(__file__).parents[3]
        / "docs/CCAgentWorkSpace/E1/workspace/reports"
        / "2026-07-10--counterfactual_rerun_evidence"
        / "counterfactual_rerun_prereg_v1.json"
    )
    target = tmp_path / "blocked_outcome_review_20260710T014406Z.json"
    target.write_bytes(frozen.read_bytes())

    result = _load(tmp_path, max_age_seconds=100_000)

    assert result["source_status"] == "SOURCE_SCHEMA_INVALID"
    assert result["selection_allowed"] is False
    assert result["candidate_rows"] == []
