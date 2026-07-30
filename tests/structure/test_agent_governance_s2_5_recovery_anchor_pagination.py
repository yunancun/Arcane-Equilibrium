"""Authenticated recovery anchor 的 genesis-to-latest pagination checks。"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
TESTS = Path(__file__).resolve().parent
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, TESTS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_5_recovery_anchor as anchor  # noqa: E402
from s2_5_recovery_anchor_testkit import (  # noqa: E402
    FakeClock,
    FakeReader,
    FakeVerifier,
    FakeWriter,
    chain,
    manifest,
)


def test_public_api_has_no_identity_key_path_sequence_head_or_nonce_inputs():
    forbidden = {"identity", "key", "path", "sequence", "head", "nonce", "cursor"}
    for method in (
        anchor.AuthenticatedRecoveryAnchor.enumerate,
        anchor.AuthenticatedRecoveryAnchor.append,
    ):
        assert forbidden.isdisjoint(inspect.signature(method).parameters)


def test_authenticated_multi_page_enumeration_walks_genesis_to_latest():
    records = chain(3)
    reader = FakeReader(records)
    verifier = FakeVerifier()
    clock = FakeClock()
    protocol = anchor.AuthenticatedRecoveryAnchor(
        writer=FakeWriter(),
        reader=reader,
        verifier=verifier,
        clock=clock,
    )

    result = protocol.enumerate(manifest())

    assert result["status"] == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    assert result["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert [item["entry"]["sequence"] for item in result["records"]] == [1, 2, 3]
    assert result["latest"]["head_digest"] == result["records"][-1]["head_digest"]
    assert reader.page_calls == [
        (None, result["latest"]["snapshot_id"]),
        (
            reader.page_values[0]["cursor_out"],
            result["latest"]["snapshot_id"],
        ),
    ]
    assert verifier.calls == ["anchor_latest", "anchor_page", "anchor_page"]
    assert clock.calls >= 3
