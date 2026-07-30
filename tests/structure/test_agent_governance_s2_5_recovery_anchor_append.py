"""Recovery anchor compare-append + exact readback effect-chain tests。"""

from __future__ import annotations

import copy
import json
import sys
from datetime import timedelta
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
    AppendingFakeWriter,
    DIGEST,
    FakeClock,
    FakeVerifier,
    MutableAnchorBackend,
    MutableFakeReader,
    WRITER_FINGERPRINT,
    identity,
    manifest,
    seal,
    signed,
)


def _protocol(*, response_status: str = "APPENDED"):
    backend = MutableAnchorBackend()
    reader = MutableFakeReader(backend)
    writer = AppendingFakeWriter(backend, response_status=response_status)
    verifier = FakeVerifier()
    protocol = anchor.AuthenticatedRecoveryAnchor(
        writer=writer,
        reader=reader,
        verifier=verifier,
        clock=FakeClock(),
    )
    return protocol, backend, writer, reader, verifier


def _execute(protocol, manifest_value=None):
    prepared = protocol.prepare_append(manifest_value or manifest())
    return prepared, protocol.execute_prepared(prepared)


def test_legacy_append_convenience_refuses_before_any_writer_effect():
    protocol, backend, writer, _, _ = _protocol()
    with pytest.raises(anchor.RecoveryAnchorError, match="prepared_packet_required"):
        protocol.append(manifest())
    assert writer.requests == []
    assert backend.records == []


def test_prepare_append_emits_closed_exact_packet_before_any_writer_effect():
    protocol, backend, writer, _, _ = _protocol()
    prepared = protocol.prepare_append(manifest())
    assert prepared["schema_version"] == "s2_5_recovery_anchor_prepared_append_v1"
    assert prepared["status"] == "PREPARED_NO_EFFECT"
    assert prepared["effect_executed"] is False
    assert anchor.validate_local_artifact(prepared) == []
    assert writer.requests == []
    assert backend.records == []


def test_execute_prepared_uses_the_identical_persistable_request():
    protocol, backend, writer, _, _ = _protocol()
    prepared = protocol.prepare_append(manifest())
    expected_request = json.loads(
        prepared["prepared_payload_json"]
    )["request"]

    packet = protocol.execute_prepared(prepared)

    assert writer.requests == [expected_request]
    assert len(backend.records) == 1
    assert packet["result"]["prepared_packet_digest"] == prepared["self_digest"]
    assert packet["postcheck"]["status"] == "UNVERIFIED"


def test_execute_prepared_rejects_expired_intent_before_writer_effect():
    protocol, backend, writer, _, _ = _protocol()
    prepared = protocol.prepare_append(manifest())
    protocol._clock.value += timedelta(minutes=6)

    packet = protocol.execute_prepared(prepared)

    assert packet["status"] == "RECOVERY_REQUIRED"
    assert packet["result"]["status"] == "RECOVERY_REQUIRED"
    assert packet["failure_detail_code"] == "anchor_append_intent_stale"
    assert writer.requests == []
    assert backend.records == []


def test_lost_response_reconciles_and_retries_only_the_exact_prepared_request():
    backend = MutableAnchorBackend()

    class CommitThenLoseResponse(AppendingFakeWriter):
        def compare_append(self, *, request):
            super().compare_append(request=request)
            raise ConnectionError("response_lost_after_commit")

    first_writer = CommitThenLoseResponse(backend)
    first = anchor.AuthenticatedRecoveryAnchor(
        writer=first_writer,
        reader=MutableFakeReader(backend),
        verifier=FakeVerifier(),
        clock=FakeClock(),
    )
    prepared = first.prepare_append(manifest())
    expected_request = json.loads(prepared["prepared_payload_json"])["request"]

    ambiguous = first.execute_prepared(prepared)

    assert ambiguous["result"]["status"] == "AMBIGUOUS_COMMITTED"
    assert first_writer.requests == [expected_request]
    assert len(backend.records) == 1

    retry_writer = AppendingFakeWriter(backend)
    retry_protocol = anchor.AuthenticatedRecoveryAnchor(
        writer=retry_writer,
        reader=MutableFakeReader(backend),
        verifier=FakeVerifier(),
        clock=FakeClock(),
    )
    reconciled = retry_protocol.reconcile_prepared(prepared)
    retried = retry_protocol.execute_prepared(prepared)

    assert reconciled["result"]["status"] == "RECONCILED_EXACT_UNVERIFIED"
    assert reconciled["result"]["object_id"] == backend.records[0]["object_id"]
    assert reconciled["result"]["version_id"] == backend.records[0]["version_id"]
    assert retry_writer.requests == [expected_request]
    assert retried["result"]["status"] == "IDEMPOTENT_EXACT"
    assert len(backend.records) == 1
    assert backend.records[0]["idempotency_key"] == expected_request["idempotency_key"]


def test_compare_append_has_complete_typed_chain_and_fresh_full_readback():
    protocol, backend, writer, reader, verifier = _protocol()

    prepared, packet = _execute(protocol)

    assert packet["status"] == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    assert packet["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert packet["result"]["status"] == "APPENDED"
    assert packet["result"]["prepared_packet_digest"] == prepared["self_digest"]
    assert packet["result"]["authenticated_response"] is False
    assert packet["readback"]["status"] == "UNVERIFIED"
    assert packet["postcheck"]["status"] == "UNVERIFIED"
    assert packet["rollback"]["status"] == "NOT_REQUIRED"
    assert packet["rollback"]["immutable_anchor_deleted"] is False
    assert packet["rollback"]["deletion_attempted"] is False
    assert backend.delete_calls == 0
    assert len(backend.records) == 1
    assert reader.exact_calls == [(
        packet["result"]["object_id"],
        packet["result"]["version_id"],
    )]
    assert packet["enumeration"]["records"][0]["entry"] == packet["entry"]
    assert packet["enumeration"]["latest"]["head_digest"] == packet["result"]["head_digest"]
    assert verifier.calls == [
        "anchor_latest",
        "anchor_compare_append",
        "anchor_exact_read",
        "anchor_latest",
        "anchor_page",
    ]
    assert set(writer.requests[0]) == {
        "schema_version", "anchor_store_id", "anchor_collection_id",
        "expected_snapshot_id", "expected_latest_version_id",
        "expected_sequence", "expected_head_digest", "idempotency_key", "entry",
    }
    assert all(
        anchor.validate_local_artifact(packet[name]) == []
        for name in ("intent", "result", "readback", "postcheck", "rollback")
    )
    assert all(
        packet[name]["side_effect_class"] == "DISPOSABLE_TEST"
        and packet[name]["production_effect"] is False
        and packet[name]["production_effect_count"] == 0
        for name in ("intent", "result", "readback", "postcheck", "rollback")
    )


def test_local_injected_capabilities_can_never_emit_pass_or_identity_distinct():
    protocol, _, _, _, _ = _protocol()
    _, packet = _execute(protocol)
    assert packet["status"] == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    assert packet["readback"]["status"] == "UNVERIFIED"
    assert packet["postcheck"]["status"] == "UNVERIFIED"
    assert packet["postcheck"]["identity_distinct"] is False
    assert (
        packet["postcheck"]["failure_code"]
        == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
    )


def test_caller_capability_identity_methods_are_never_read_as_authority():
    class PoisonIdentityWriter(AppendingFakeWriter):
        def identity(self):
            raise AssertionError("caller writer identity must not be read")

    class PoisonIdentityReader(MutableFakeReader):
        def identity(self):
            raise AssertionError("caller reader identity must not be read")

    class PoisonIdentityVerifier(FakeVerifier):
        def identity(self):
            raise AssertionError("caller verifier identity must not be read")

    backend = MutableAnchorBackend()
    protocol = anchor.AuthenticatedRecoveryAnchor(
        writer=PoisonIdentityWriter(backend),
        reader=PoisonIdentityReader(backend),
        verifier=PoisonIdentityVerifier(),
        clock=FakeClock(),
    )
    _, packet = _execute(protocol)
    assert packet["postcheck"]["status"] == "UNVERIFIED"
    assert packet["postcheck"]["identity_distinct"] is False


def test_idempotent_exact_is_the_only_accepted_retry_status():
    protocol, backend, _, _, _ = _protocol(response_status="IDEMPOTENT_EXACT")
    _, packet = _execute(protocol)
    assert packet["result"]["status"] == "IDEMPOTENT_EXACT"
    assert packet["postcheck"]["status"] == "UNVERIFIED"
    assert len(backend.records) == 1


@pytest.mark.parametrize("status", ["CONFLICT", "HEAD_RACE", "ALREADY_EXISTS"])
def test_conflict_or_non_exact_retry_status_is_a_typed_recovery_block(status):
    protocol, backend, _, _, _ = _protocol(response_status=status)
    _, packet = _execute(protocol)
    assert packet["status"] == "RECOVERY_REQUIRED"
    assert packet["result"]["status"] == "RECOVERY_REQUIRED"
    assert packet["readback"]["status"] == "NOT_PERFORMED"
    assert packet["postcheck"]["status"] == "NOT_PERFORMED"
    assert packet["rollback"]["status"] == "RECOVERY_REQUIRED"
    assert packet["rollback"]["immutable_anchor_deleted"] is False
    assert backend.delete_calls == 0


def test_compare_append_signature_failure_is_a_typed_ambiguous_recovery():
    protocol, backend, writer, _, _ = _protocol()
    original = writer.compare_append

    def tampered(*, request):
        envelope = original(request=request)
        envelope["signature"] = DIGEST
        return envelope

    writer.compare_append = tampered
    _, packet = _execute(protocol)
    assert packet["status"] == "RECOVERY_REQUIRED"
    assert packet["result"]["status"] == "AMBIGUOUS_COMMITTED"
    assert packet["result"]["authenticated_response"] is False
    assert packet["rollback"]["status"] == "RECOVERY_REQUIRED"
    assert len(backend.records) == 1


@pytest.mark.parametrize("field", ["expected_sequence", "expected_head_digest"])
def test_signed_compare_append_head_race_binding_is_rejected(field):
    protocol, backend, writer, _, _ = _protocol()
    original = writer.compare_append

    def raced(*, request):
        envelope = original(request=request)
        payload = copy.deepcopy(envelope["payload"])
        payload[field] = 99 if field == "expected_sequence" else DIGEST
        payload = seal(payload)
        return signed(
            payload,
            purpose="anchor_compare_append",
            fingerprint=WRITER_FINGERPRINT,
        )

    writer.compare_append = raced
    _, packet = _execute(protocol)
    assert packet["status"] == "RECOVERY_REQUIRED"
    assert packet["result"]["status"] == "AMBIGUOUS_COMMITTED"
    assert packet["failure_detail_code"].endswith("binding_mismatch")
    assert packet["rollback"]["deletion_attempted"] is False
    assert len(backend.records) == 1


@pytest.mark.parametrize("case", ["version_mismatch", "signature_invalid"])
def test_post_append_exact_read_failure_preserves_append_fact_and_requires_recovery(case):
    protocol, backend, _, reader, _ = _protocol()
    original = reader.read_signed_exact

    def broken_exact(*, object_id, version_id):
        envelope = original(object_id=object_id, version_id=version_id)
        if case == "signature_invalid":
            envelope["signature"] = DIGEST
            return envelope
        payload = copy.deepcopy(envelope["payload"])
        payload["record"]["version_id"] = "s2-5-anchor-version-" + "9" * 64
        payload = seal(payload)
        return signed(payload, purpose="anchor_exact_read")

    reader.read_signed_exact = broken_exact
    _, packet = _execute(protocol)
    assert packet["status"] == "RECOVERY_REQUIRED"
    assert packet["result"]["status"] == "APPENDED"
    assert packet["result"]["authenticated_response"] is False
    assert packet["readback"]["status"] == "RECOVERY_REQUIRED"
    assert packet["rollback"]["status"] == "RECOVERY_REQUIRED"
    assert packet["rollback"]["immutable_anchor_deleted"] is False
    assert len(backend.records) == 1


def test_capabilities_must_be_distinct_objects():
    backend = MutableAnchorBackend()
    writer = AppendingFakeWriter(backend)
    reader = MutableFakeReader(backend)
    with pytest.raises(anchor.RecoveryAnchorError, match="capabilities_must_be_distinct"):
        anchor.AuthenticatedRecoveryAnchor(
            writer=writer,
            reader=reader,
            verifier=writer,
            clock=FakeClock(),
        )


def test_arbitrary_shared_caller_owner_key_and_process_cannot_create_pass():
    shared_claim = {
        "owner": "caller-owner",
        "key_fingerprint": "sha256:" + "9" * 64,
        "process_id": 999,
        "uid": 0,
        "cgroup": "/caller/chosen",
    }

    class ArbitraryClaimWriter(AppendingFakeWriter):
        def identity(self):
            return dict(shared_claim)

    class ArbitraryClaimReader(MutableFakeReader):
        def identity(self):
            return dict(shared_claim)

    class ArbitraryClaimVerifier(FakeVerifier):
        def identity(self):
            return dict(shared_claim)

    backend = MutableAnchorBackend()
    protocol = anchor.AuthenticatedRecoveryAnchor(
        writer=ArbitraryClaimWriter(backend),
        reader=ArbitraryClaimReader(backend),
        verifier=ArbitraryClaimVerifier(),
        clock=FakeClock(),
    )
    _, packet = _execute(protocol)
    assert packet["readback"]["status"] == "UNVERIFIED"
    assert packet["postcheck"]["status"] == "UNVERIFIED"
    assert packet["postcheck"]["identity_distinct"] is False
    assert packet["readback"]["reader_identity"]["key_fingerprint"] is None


def test_nonce_and_idempotency_are_derived_repeatably_not_caller_supplied():
    first, _, _, _, _ = _protocol()
    second, _, _, _, _ = _protocol()
    _, first_packet = _execute(first)
    _, second_packet = _execute(second)
    assert first_packet["entry"]["nonce"] == second_packet["entry"]["nonce"]
    assert (
        first_packet["intent"]["idempotency_key"]
        == second_packet["intent"]["idempotency_key"]
    )
    assert anchor.validate_local_artifact(first_packet["intent"]) == []


def test_cross_source_manifest_is_rejected_before_writer_effect():
    protocol, backend, writer, _, _ = _protocol()
    cross_source = manifest()
    cross_source["source_head"] = "9" * 40
    cross_source = seal(cross_source)
    with pytest.raises(anchor.RecoveryAnchorError):
        protocol.prepare_append(cross_source)
    assert writer.requests == []
    assert backend.records == []


def test_no_artifact_can_claim_external_or_platform_attestation():
    protocol, _, _, _, _ = _protocol()
    _, packet = _execute(protocol)

    def strings(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, str):
            yield value

    assert "PLATFORM_OR_EXTERNAL_ATTESTED" not in set(strings(packet))
    assert packet["status"] == "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"


def test_resealed_writer_signer_metadata_mismatch_never_authenticates():
    protocol, backend, writer, _, _ = _protocol()
    original = writer.compare_append

    def mismatched(*, request):
        envelope = original(request=request)
        payload = copy.deepcopy(envelope["payload"])
        payload["signer_identity"]["cgroup"] = "/caller/chosen"
        payload = seal(payload)
        return signed(
            payload,
            purpose="anchor_compare_append",
            fingerprint=WRITER_FINGERPRINT,
        )

    writer.compare_append = mismatched
    _, packet = _execute(protocol)
    assert packet["status"] == "RECOVERY_REQUIRED"
    assert packet["result"]["status"] == "AMBIGUOUS_COMMITTED"
    assert packet["result"]["authenticated_response"] is False
    assert len(backend.records) == 1
