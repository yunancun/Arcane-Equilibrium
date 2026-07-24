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


def test_replay_timestamp_is_captured_after_trusted_finalization(
    monkeypatch,
) -> None:
    events: list[str] = []
    replay_time = datetime(2026, 7, 24, 1, 2, 3, tzinfo=timezone.utc)
    expected_result = {"status": "PASS", "errors": []}

    def fake_finalize(*_args, **_kwargs):
        events.append("trusted-finalization")
        return expected_result

    def fake_now() -> datetime:
        events.append("replay-timestamp")
        assert events == ["trusted-finalization", "replay-timestamp"]
        return replay_time

    monkeypatch.setattr(
        finalizer.trusted,
        "finalize_s1_target_host_from_host_inputs",
        fake_finalize,
    )
    monkeypatch.setattr(finalizer, "_now", fake_now)

    result, evaluated_at = finalizer._finalize_and_capture_replay_time(
        {},
        {},
        signature=b"signed",
        github_token=b"token",
    )

    assert result is expected_result
    assert evaluated_at == replay_time
