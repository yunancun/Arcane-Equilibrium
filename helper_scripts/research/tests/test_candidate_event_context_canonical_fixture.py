"""Rust/Python 共用 candidate_event_context canonical fixture parity。"""

from __future__ import annotations

import json
from pathlib import Path

from cost_gate_learning_lane.candidate_evaluation_context import (
    _canonical_bytes,
    canonical_sha256,
)


FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "rust/openclaw_engine/tests/fixtures/candidate_event_context_v1/canonical_fixture.json"
)


def test_shared_rust_python_candidate_event_context_canonical_fixture() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    canonical = _canonical_bytes(fixture["input"])

    assert canonical == fixture["expected_canonical_json"].encode("utf-8")
    assert canonical_sha256(fixture["input"]) == fixture["expected_sha256"]
