"""Recovery-anchor authenticated pagination 的 mutation/security matrix。"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
TESTS = Path(__file__).resolve().parent
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, TESTS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_5_recovery_anchor as anchor  # noqa: E402
from s2_5_recovery_anchor_testkit import (  # noqa: E402
    DIGEST,
    FakeClock,
    FakeReader,
    FakeVerifier,
    FakeWriter,
    chain,
    head_digest,
    manifest,
    pages,
    seal,
    signed,
)


def _protocol(reader):
    return anchor.AuthenticatedRecoveryAnchor(
        writer=FakeWriter(),
        reader=reader,
        verifier=FakeVerifier(),
        clock=FakeClock(),
    )


def _reseal_record(record):
    record["entry"] = seal(record["entry"])
    record["checksum"] = anchor.central_validator.canonical_digest(record["entry"])
    record["head_digest"] = head_digest(record["entry"])


@pytest.mark.parametrize(
    "case",
    [
        "latest_stale",
        "latest_future",
        "latest_cross_store",
        "latest_cross_root",
        "latest_cross_source",
        "latest_cross_profile",
        "latest_page_math_drift",
        "page_early_terminal",
        "page_late_terminal",
        "page_cursor_repeat",
        "page_cursor_gap",
        "page_snapshot_drift",
        "page_count_drift",
        "page_cross_source",
        "sequence_gap",
        "predecessor_fork",
        "duplicate_object",
        "duplicate_version",
        "entry_count_drift",
    ],
)
def test_authenticated_pagination_mutations_fail_closed(case):
    records = chain(5 if case == "page_cursor_repeat" else 3)
    reader = FakeReader(records)

    if case.startswith("latest_"):
        latest_value = copy.deepcopy(reader.latest_value)
        if case == "latest_stale":
            latest_value["expires_at"] = "2029-12-31T23:59:59+00:00"
        elif case == "latest_future":
            latest_value["issued_at"] = "2030-01-01T00:03:01+00:00"
            latest_value["expires_at"] = "2030-01-01T00:05:00+00:00"
        elif case == "latest_cross_store":
            latest_value["store_id"] = "s2-5-store-" + "9" * 64
        elif case == "latest_cross_root":
            latest_value["state_root_id"] = DIGEST
        elif case == "latest_cross_source":
            latest_value["source_head"] = "9" * 40
        elif case == "latest_page_math_drift":
            latest_value["page_size"] = 3
        else:
            latest_value["target_profile_id"] = "wrong-profile"
        reader.latest_value = seal(latest_value)
    else:
        page_index = 1 if case in {
            "page_late_terminal", "page_cursor_gap", "page_cross_source"
        } else 0
        page = copy.deepcopy(reader.page_values[page_index])
        if case == "page_early_terminal":
            page["cursor_out"] = None
        elif case == "page_late_terminal":
            page["cursor_out"] = "s2-5-anchor-cursor-" + "9" * 64
        elif case == "page_cursor_repeat":
            page_index = 1
            page = copy.deepcopy(reader.page_values[1])
            page["cursor_out"] = page["cursor_in"]
        elif case == "page_cursor_gap":
            page["cursor_in"] = "s2-5-anchor-cursor-" + "9" * 64
        elif case == "page_snapshot_drift":
            page["snapshot_id"] = DIGEST
        elif case == "page_count_drift":
            page["page_count"] += 1
        elif case == "page_cross_source":
            page["source_head"] = "9" * 40
        elif case == "sequence_gap":
            page["records"][1]["entry"]["sequence"] = 3
            _reseal_record(page["records"][1])
        elif case == "predecessor_fork":
            page["records"][1]["entry"]["previous_anchor_digest"] = DIGEST
            _reseal_record(page["records"][1])
        elif case == "duplicate_object":
            page["records"][1]["object_id"] = page["records"][0]["object_id"]
        elif case == "duplicate_version":
            page["records"][1]["version_id"] = page["records"][0]["version_id"]
        elif case == "entry_count_drift":
            page["records"].pop()
        reader.page_values[page_index] = seal(page)
        if case == "page_cursor_gap":
            calls = 0

            def sequential_page(*, cursor, snapshot_id):
                nonlocal calls
                selected = reader.page_values[calls]
                calls += 1
                return signed(selected, purpose="anchor_page")

            reader.read_signed_page = sequential_page

    with pytest.raises(anchor.RecoveryAnchorError):
        _protocol(reader).enumerate(manifest())


@pytest.mark.parametrize("surface", ["latest", "page"])
def test_signed_surface_tampering_fails_before_payload_trust(surface):
    reader = FakeReader(chain(3))
    if surface == "latest":
        original = reader.read_signed_latest

        def tampered_latest():
            envelope = original()
            envelope["signature"] = DIGEST
            return envelope

        reader.read_signed_latest = tampered_latest
    else:
        original = reader.read_signed_page

        def tampered_page(*, cursor, snapshot_id):
            envelope = original(cursor=cursor, snapshot_id=snapshot_id)
            envelope["signature"] = DIGEST
            return envelope

        reader.read_signed_page = tampered_page
    with pytest.raises(anchor.RecoveryAnchorError, match="signature"):
        _protocol(reader).enumerate(manifest())


def test_empty_genesis_snapshot_is_valid_and_reads_no_page():
    reader = FakeReader([])
    result = _protocol(reader).enumerate(manifest())
    assert result["records"] == []
    assert result["latest"]["sequence"] == 0
    assert reader.page_calls == []


def test_fresh_instance_old_prefix_never_claims_a_durable_monotonic_floor():
    newer = _protocol(FakeReader(chain(3))).enumerate(manifest())
    older = _protocol(FakeReader(chain(2))).enumerate(manifest())

    assert newer["status"] == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    assert older["status"] == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    assert (
        newer["monotonic_floor_status"]
        == older["monotonic_floor_status"]
        == "UNVERIFIED_DURABLE_MONOTONIC_FLOOR_REQUIRED"
    )
    assert newer["latest"]["sequence"] == 3
    assert older["latest"]["sequence"] == 2


def test_same_sequence_different_latest_head_fails_snapshot_consistency():
    reader = FakeReader(chain(3))
    protocol = _protocol(reader)
    protocol.enumerate(manifest())
    latest_value = copy.deepcopy(reader.latest_value)
    latest_value["head_digest"] = DIGEST
    reader.latest_value = seal(latest_value)
    with pytest.raises(anchor.RecoveryAnchorError, match="drift|mismatch"):
        protocol.enumerate(manifest())


def test_page_record_entry_schema_version_downgrade_is_rejected():
    reader = FakeReader(chain(3))
    page = copy.deepcopy(reader.page_values[0])
    page["records"][0]["entry"]["schema_version"] = (
        "s2_5_recovery_anchor_entry_v1"
    )
    _reseal_record(page["records"][0])
    reader.page_values[0] = seal(page)
    with pytest.raises(anchor.RecoveryAnchorError):
        _protocol(reader).enumerate(manifest())
