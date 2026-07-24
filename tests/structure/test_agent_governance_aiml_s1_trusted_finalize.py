"""Governed replay-safe timestamp binding for the S1 trusted finalizer."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import aiml_s1_trusted_finalize as finalizer  # noqa: E402


def test_replay_timestamp_is_the_signed_bundle_issue_time(
    monkeypatch,
) -> None:
    events: list[str] = []
    replay_time = datetime(2026, 7, 24, 1, 2, 3, tzinfo=timezone.utc)
    expected_result = {"status": "PASS", "errors": []}
    bundle = {"issued_at": replay_time.isoformat().replace("+00:00", "Z")}

    def fake_finalize(*_args, **_kwargs):
        events.append("trusted-finalization")
        return expected_result

    monkeypatch.setattr(
        finalizer.trusted,
        "finalize_s1_target_host_from_host_inputs",
        fake_finalize,
    )

    result, evaluated_at = finalizer._finalize_and_capture_replay_time(
        {},
        bundle,
        signature=b"signed",
        github_token=b"token",
    )

    assert result is expected_result
    assert evaluated_at == replay_time
    assert events == ["trusted-finalization"]


def test_replay_timestamp_rejects_an_unsigned_or_malformed_bundle_time(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        finalizer.trusted,
        "finalize_s1_target_host_from_host_inputs",
        lambda *_args, **_kwargs: {"status": "PASS", "errors": []},
    )

    for bundle in ({}, {"issued_at": "not-a-time"}):
        try:
            finalizer._finalize_and_capture_replay_time(
                {},
                bundle,
                signature=b"signed",
                github_token=b"token",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("malformed signed evaluation time was accepted")
